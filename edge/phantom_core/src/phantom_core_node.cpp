#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/nav_sat_fix.hpp>
#include <geometry_msgs/msg/twist_with_covariance_stamped.hpp>
#include <std_msgs/msg/bool.hpp>
#include "phantom_msgs/msg/state_estimate.hpp"
#include "phantom_core/ekf.hpp"
#include <chrono>

using namespace std::chrono_literals;
using namespace phantom_core;

// ─────────────────────────────────────────────────────────────
// PhantomCore™ Node
// ROS 2 wrapper around the EKF for state estimation.
// Runs at IMU rate (100–500 Hz), publishes /state/estimate.
// ─────────────────────────────────────────────────────────────
class PhantomCoreNode : public rclcpp::Node {
public:
    PhantomCoreNode() : Node("phantom_core_node")
    {
        // Parameters
        declare_parameter("imu_topic",      "/imu/data");
        declare_parameter("gnss_fix_topic", "/gnss/fix");
        declare_parameter("gnss_vel_topic", "/gnss/velocity");
        declare_parameter("output_topic",   "/state/estimate");
        declare_parameter("accel_noise",    0.1);
        declare_parameter("gyro_noise",     0.01);
        declare_parameter("accel_bias_rw",  1e-4);
        declare_parameter("gyro_bias_rw",   1e-5);
        declare_parameter("gnss_pos_noise", 2.0);
        declare_parameter("gnss_vel_noise", 0.1);

        // Configure EKF noise from params
        ekf_.set_process_noise(
            get_parameter("accel_noise").as_double(),
            get_parameter("gyro_noise").as_double(),
            get_parameter("accel_bias_rw").as_double(),
            get_parameter("gyro_bias_rw").as_double()
        );
        ekf_.set_gnss_noise(
            get_parameter("gnss_pos_noise").as_double(),
            get_parameter("gnss_vel_noise").as_double()
        );

        // Publisher
        state_pub_ = create_publisher<phantom_msgs::msg::StateEstimate>(
            get_parameter("output_topic").as_string(), rclcpp::QoS(10));

        // IMU subscriber (high-rate, real-time)
        imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(
            get_parameter("imu_topic").as_string(),
            rclcpp::QoS(10).best_effort(),
            [this](const sensor_msgs::msg::Imu::SharedPtr msg) {
                on_imu(msg);
            });

        // GNSS fix subscriber
        gnss_fix_sub_ = create_subscription<sensor_msgs::msg::NavSatFix>(
            get_parameter("gnss_fix_topic").as_string(),
            rclcpp::QoS(10).best_effort(),
            [this](const sensor_msgs::msg::NavSatFix::SharedPtr msg) {
                on_gnss_fix(msg);
            });

        // GNSS velocity
        gnss_vel_sub_ = create_subscription<
                geometry_msgs::msg::TwistWithCovarianceStamped>(
            get_parameter("gnss_vel_topic").as_string(),
            rclcpp::QoS(10).best_effort(),
            [this](const geometry_msgs::msg::TwistWithCovarianceStamped::SharedPtr msg) {
                on_gnss_vel(msg);
            });

        RCLCPP_INFO(get_logger(), "PhantomCore™ initialized — waiting for GNSS fix...");
    }

private:
    ExtendedKalmanFilter ekf_;

    // Buffered GNSS state
    GnssMeasurement gnss_buf_{};
    bool gnss_initialized_ = false;

    // Last GNSS fix origin for NED projection
    double origin_lat_ = 0.0;
    double origin_lon_ = 0.0;
    double origin_alt_ = 0.0;
    bool   origin_set_ = false;

    rclcpp::Publisher<phantom_msgs::msg::StateEstimate>::SharedPtr state_pub_;
    rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
    rclcpp::Subscription<sensor_msgs::msg::NavSatFix>::SharedPtr gnss_fix_sub_;
    rclcpp::Subscription<
        geometry_msgs::msg::TwistWithCovarianceStamped>::SharedPtr gnss_vel_sub_;

    // ── IMU callback: EKF predict step ────────────────────────
    void on_imu(const sensor_msgs::msg::Imu::SharedPtr msg)
    {
        if (!ekf_.state().initialized) return;

        ImuMeasurement imu;
        imu.ax = msg->linear_acceleration.x;
        imu.ay = msg->linear_acceleration.y;
        imu.az = msg->linear_acceleration.z;
        imu.gx = msg->angular_velocity.x;
        imu.gy = msg->angular_velocity.y;
        imu.gz = msg->angular_velocity.z;
        imu.timestamp_s = rclcpp::Time(msg->header.stamp).seconds();

        ekf_.predict(imu);
        publish_state(msg->header.stamp);
    }

    // ── GNSS fix callback: LLA → NED + EKF update ────────────
    void on_gnss_fix(const sensor_msgs::msg::NavSatFix::SharedPtr msg)
    {
        if (msg->status.status < 0) {    // No fix
            gnss_buf_.valid = false;
            return;
        }

        if (!origin_set_) {
            origin_lat_ = msg->latitude;
            origin_lon_ = msg->longitude;
            origin_alt_ = msg->altitude;
            origin_set_ = true;
            RCLCPP_INFO(get_logger(), "GNSS origin set: %.6f, %.6f, %.2f",
                        origin_lat_, origin_lon_, origin_alt_);
        }

        // LLA → NED (flat-earth approximation, valid < 10 km)
        constexpr double R_earth = 6371000.0;
        constexpr double DEG2RAD = M_PI / 180.0;
        double dlat = (msg->latitude  - origin_lat_) * DEG2RAD;
        double dlon = (msg->longitude - origin_lon_) * DEG2RAD;
        double cos_lat = std::cos(origin_lat_ * DEG2RAD);

        gnss_buf_.x = dlat * R_earth;
        gnss_buf_.y = dlon * R_earth * cos_lat;
        gnss_buf_.z = -(msg->altitude - origin_alt_);   // NED: down is +z

        gnss_buf_.pos_accuracy_m = std::sqrt(msg->position_covariance[0]);
        gnss_buf_.valid          = true;
        gnss_buf_.timestamp_s    = rclcpp::Time(msg->header.stamp).seconds();

        if (!ekf_.state().initialized) {
            ekf_.initialize(gnss_buf_);
            RCLCPP_INFO(get_logger(), "PhantomCore™ EKF initialized from GNSS.");
        } else {
            ekf_.update_gnss(gnss_buf_);
        }
    }

    // ── GNSS velocity callback ────────────────────────────────
    void on_gnss_vel(
        const geometry_msgs::msg::TwistWithCovarianceStamped::SharedPtr msg)
    {
        gnss_buf_.vx = msg->twist.twist.linear.x;
        gnss_buf_.vy = msg->twist.twist.linear.y;
        gnss_buf_.vz = msg->twist.twist.linear.z;
        gnss_buf_.vel_accuracy_ms = std::sqrt(msg->twist.covariance[0]);
    }

    // ── Publish state estimate ─────────────────────────────────
    void publish_state(const rclcpp::Time& stamp)
    {
        const auto& s = ekf_.state();
        auto msg = phantom_msgs::msg::StateEstimate();
        msg.header.stamp    = stamp;
        msg.header.frame_id = "ned";

        msg.x  = s.x(0);  msg.y  = s.x(1);  msg.z  = s.x(2);
        msg.vx = s.x(3);  msg.vy = s.x(4);  msg.vz = s.x(5);
        msg.qw = s.x(6);  msg.qx = s.x(7);
        msg.qy = s.x(8);  msg.qz = s.x(9);

        msg.gnss_valid       = gnss_buf_.valid;
        msg.gnss_accuracy_m  = gnss_buf_.pos_accuracy_m;

        // Flatten 6x6 covariance (pos + orient)
        auto cov6x6 = ekf_.pose_covariance();
        for (int i = 0; i < 6; i++)
            for (int j = 0; j < 6; j++)
                msg.covariance[i * 6 + j] = cov6x6(i, j);

        state_pub_->publish(msg);
    }
};

// ─────────────────────────────────────────────────────────────
int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PhantomCoreNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
