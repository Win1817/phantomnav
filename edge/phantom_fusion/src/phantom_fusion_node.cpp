#include <rclcpp/rclcpp.hpp>
#include "phantom_msgs/msg/state_estimate.hpp"
#include "phantom_msgs/msg/slam_pose.hpp"
#include "phantom_msgs/msg/fused_pose.hpp"
#include <Eigen/Dense>
#include <mutex>
#include <optional>

// ─────────────────────────────────────────────────────────────
// PhantomFusion™ Node
// Combines INS (/state/estimate) and SLAM (/slam/pose) into
// a unified /fusion/pose via adaptive covariance-weighted fusion.
//
// Fusion formula:
//   pose_fused = w_ins * pose_ins + w_slam * pose_slam
//   w_ins  = sigma_slam² / (sigma_ins² + sigma_slam²)
//   w_slam = sigma_ins²  / (sigma_ins² + sigma_slam²)
// ─────────────────────────────────────────────────────────────

class PhantomFusionNode : public rclcpp::Node {
public:
    PhantomFusionNode() : Node("phantom_fusion_node")
    {
        declare_parameter("publish_rate_hz",    50.0);
        declare_parameter("slam_weight_min",    0.05);
        declare_parameter("slam_weight_max",    0.9);
        declare_parameter("quality_threshold",  0.3);
        declare_parameter("drift_window_s",     30.0);
        declare_parameter("slam_align_timeout", 5.0);

        slam_weight_min_ = get_parameter("slam_weight_min").as_double();
        slam_weight_max_ = get_parameter("slam_weight_max").as_double();
        quality_threshold_ = get_parameter("quality_threshold").as_double();

        // Publishers
        fused_pub_ = create_publisher<phantom_msgs::msg::FusedPose>(
            "/fusion/pose", rclcpp::QoS(10));

        // Subscribers
        ins_sub_ = create_subscription<phantom_msgs::msg::StateEstimate>(
            "/state/estimate", rclcpp::QoS(20).best_effort(),
            [this](phantom_msgs::msg::StateEstimate::SharedPtr msg) {
                std::lock_guard<std::mutex> lk(mtx_);
                latest_ins_ = msg;
            });

        slam_sub_ = create_subscription<phantom_msgs::msg::SlamPose>(
            "/slam/pose", rclcpp::QoS(10).best_effort(),
            [this](phantom_msgs::msg::SlamPose::SharedPtr msg) {
                std::lock_guard<std::mutex> lk(mtx_);
                on_slam(msg);
            });

        // Periodic fusion timer
        double hz = get_parameter("publish_rate_hz").as_double();
        fusion_timer_ = create_wall_timer(
            std::chrono::duration<double>(1.0 / hz),
            [this]() { fuse_and_publish(); });

        RCLCPP_INFO(get_logger(), "PhantomFusion™ initialized at %.0f Hz.", hz);
    }

private:
    std::mutex mtx_;
    phantom_msgs::msg::StateEstimate::SharedPtr latest_ins_;
    phantom_msgs::msg::SlamPose::SharedPtr       latest_slam_;

    // SLAM ↔ INS coordinate alignment (scale + rotation)
    Eigen::Vector3d slam_offset_ = Eigen::Vector3d::Zero();
    bool slam_aligned_ = false;
    double slam_align_time_ = 0.0;

    // Drift tracking
    Eigen::Vector3d drift_accum_ = Eigen::Vector3d::Zero();
    double last_drift_check_time_ = 0.0;

    double slam_weight_min_;
    double slam_weight_max_;
    double quality_threshold_;

    rclcpp::Publisher<phantom_msgs::msg::FusedPose>::SharedPtr fused_pub_;
    rclcpp::Subscription<phantom_msgs::msg::StateEstimate>::SharedPtr ins_sub_;
    rclcpp::Subscription<phantom_msgs::msg::SlamPose>::SharedPtr slam_sub_;
    rclcpp::TimerBase::SharedPtr fusion_timer_;

    // ── SLAM callback: compute alignment offset on first valid pose ──
    void on_slam(const phantom_msgs::msg::SlamPose::SharedPtr msg)
    {
        latest_slam_ = msg;

        if (!slam_aligned_ && msg->slam_initialized && latest_ins_) {
            // Compute offset from INS origin to SLAM world frame
            slam_offset_ = Eigen::Vector3d(
                latest_ins_->x - msg->x,
                latest_ins_->y - msg->y,
                latest_ins_->z - msg->z);
            slam_aligned_   = true;
            slam_align_time_ = rclcpp::Time(msg->header.stamp).seconds();
            RCLCPP_INFO(get_logger(),
                "SLAM aligned to INS. Offset: [%.2f, %.2f, %.2f] m",
                slam_offset_.x(), slam_offset_.y(), slam_offset_.z());
        }
    }

    // ── Adaptive weight computation ────────────────────────────
    // Based on position variance from covariance matrices.
    // Higher uncertainty → lower weight.
    double compute_slam_weight(
        const phantom_msgs::msg::StateEstimate& ins,
        const phantom_msgs::msg::SlamPose& slam)
    {
        if (!slam_aligned_ || slam.quality < quality_threshold_)
            return slam_weight_min_;

        // Extract position variance (diagonal of 3x3 pos block)
        double var_ins  = ins.covariance[0] + ins.covariance[7]  + ins.covariance[14];
        double var_slam = slam.covariance[0] + slam.covariance[7] + slam.covariance[14];

        if (var_ins + var_slam < 1e-12)
            return 0.5;

        // SLAM gets higher weight when INS variance is higher
        double w_slam = var_ins / (var_ins + var_slam);

        // Scale by SLAM quality
        w_slam *= slam.quality;

        // Clamp
        return std::clamp(w_slam, slam_weight_min_, slam_weight_max_);
    }

    // ── Main fusion loop ───────────────────────────────────────
    void fuse_and_publish()
    {
        std::lock_guard<std::mutex> lk(mtx_);

        if (!latest_ins_) return;

        auto msg = phantom_msgs::msg::FusedPose();
        msg.header.stamp    = latest_ins_->header.stamp;
        msg.header.frame_id = "ned";

        bool slam_usable = latest_slam_ &&
                           latest_slam_->slam_initialized &&
                           slam_aligned_ &&
                           latest_slam_->quality >= quality_threshold_;

        double w_slam = slam_usable
            ? compute_slam_weight(*latest_ins_, *latest_slam_)
            : 0.0;
        double w_ins = 1.0 - w_slam;

        // SLAM position transformed to NED frame
        Eigen::Vector3d slam_pos_ned = Eigen::Vector3d::Zero();
        if (slam_usable) {
            slam_pos_ned = Eigen::Vector3d(
                latest_slam_->x + slam_offset_.x(),
                latest_slam_->y + slam_offset_.y(),
                latest_slam_->z + slam_offset_.z());
        }

        Eigen::Vector3d ins_pos(latest_ins_->x, latest_ins_->y, latest_ins_->z);
        Eigen::Vector3d fused_pos = w_ins * ins_pos + w_slam * slam_pos_ned;

        msg.x = fused_pos.x();
        msg.y = fused_pos.y();
        msg.z = fused_pos.z();

        // Velocity: purely from INS (SLAM velocity not directly available)
        msg.vx = latest_ins_->vx;
        msg.vy = latest_ins_->vy;
        msg.vz = latest_ins_->vz;

        // Orientation: SLAM when quality high, INS otherwise
        if (slam_usable && w_slam > 0.5) {
            msg.qw = latest_slam_->qw;
            msg.qx = latest_slam_->qx;
            msg.qy = latest_slam_->qy;
            msg.qz = latest_slam_->qz;
        } else {
            msg.qw = latest_ins_->qw;
            msg.qx = latest_ins_->qx;
            msg.qy = latest_ins_->qy;
            msg.qz = latest_ins_->qz;
        }

        // Fusion weights
        msg.w_ins  = (float)w_ins;
        msg.w_slam = (float)w_slam;

        // Drift estimate: displacement between pure INS and fused
        Eigen::Vector3d drift = ins_pos - fused_pos;
        msg.drift_estimate_m = (float)drift.norm();

        // Propagate fused covariance
        for (int i = 0; i < 36; i++) {
            double ins_cov  = latest_ins_->covariance[i];
            double slam_cov = slam_usable ? latest_slam_->covariance[i] : ins_cov * 2.0;
            msg.covariance[i] = w_ins * w_ins * ins_cov + w_slam * w_slam * slam_cov;
        }

        fused_pub_->publish(msg);
    }
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PhantomFusionNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
