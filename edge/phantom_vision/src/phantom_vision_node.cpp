#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
// cv_bridge: .h on Humble/Foxy, .hpp on Rolling/Iron
#if __has_include(<cv_bridge/cv_bridge.hpp>)
  #include <cv_bridge/cv_bridge.hpp>
#else
  #include <cv_bridge/cv_bridge.h>
#endif
#include <opencv2/opencv.hpp>
#include <opencv2/features2d.hpp>
#include "phantom_msgs/msg/slam_pose.hpp"

#include <deque>
#include <mutex>

// ─────────────────────────────────────────────────────────────
// PhantomVision™ Node
// Monocular visual odometry front-end compatible with ORB-SLAM3.
// Publishes /slam/pose and /slam/quality at camera framerate.
// ─────────────────────────────────────────────────────────────

struct TrackedFrame {
    double timestamp_s;
    std::vector<cv::KeyPoint> keypoints;
    cv::Mat descriptors;
    cv::Mat pose;          // 4x4 SE3 (world-to-camera)
    bool valid;
};

class PhantomVisionNode : public rclcpp::Node {
public:
    PhantomVisionNode() : Node("phantom_vision_node")
    {
        declare_parameter("image_topic",    "/camera/image_raw");
        declare_parameter("cam_info_topic", "/camera/camera_info");
        declare_parameter("output_pose",    "/slam/pose");
        declare_parameter("max_features",   1500);
        declare_parameter("min_features",   80);
        declare_parameter("orb_scale",      1.2);
        declare_parameter("orb_levels",     8);

        max_features_ = (int)get_parameter("max_features").as_int();
        min_features_ = (int)get_parameter("min_features").as_int();

        // ORB detector
        orb_ = cv::ORB::create(
            max_features_,
            (float)get_parameter("orb_scale").as_double(),
            (int)get_parameter("orb_levels").as_int()
        );

        // BF matcher with Hamming norm (ORB descriptors)
        matcher_ = cv::BFMatcher::create(cv::NORM_HAMMING, true);

        // Publishers
        slam_pose_pub_ = create_publisher<phantom_msgs::msg::SlamPose>(
            get_parameter("output_pose").as_string(), rclcpp::QoS(10));

        // Camera info sub (latched)
        cam_info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
            get_parameter("cam_info_topic").as_string(),
            rclcpp::QoS(1).reliable(),
            [this](const sensor_msgs::msg::CameraInfo::SharedPtr msg) {
                on_camera_info(msg);
            });

        // Image sub
        image_sub_ = create_subscription<sensor_msgs::msg::Image>(
            get_parameter("image_topic").as_string(),
            rclcpp::QoS(5).best_effort(),
            [this](const sensor_msgs::msg::Image::SharedPtr msg) {
                on_image(msg);
            });

        RCLCPP_INFO(get_logger(), "PhantomVision™ SLAM initialized.");
    }

private:
    // ORB + BFMatcher
    cv::Ptr<cv::ORB>       orb_;
    cv::Ptr<cv::BFMatcher> matcher_;

    // Intrinsic calibration
    cv::Mat K_;      // 3x3 intrinsics
    cv::Mat dist_;   // distortion coefficients
    bool   cam_calibrated_ = false;

    // Current trajectory: current pose in world frame (NED)
    cv::Mat pose_world_ = cv::Mat::eye(4, 4, CV_64F);
    bool    slam_initialized_ = false;

    // Previous frame data
    TrackedFrame prev_frame_;
    std::deque<TrackedFrame> frame_history_;
    static constexpr size_t HISTORY_SIZE = 30;

    // Feature thresholds (set from ROS parameters)
    int     max_features_       = 1500;
    int     min_features_       = 80;

    // Quality metrics
    int     tracked_features_   = 0;
    double  slam_quality_       = 0.0;
    bool    loop_closure_active_ = false;
    int     consecutive_good_   = 0;

    rclcpp::Publisher<phantom_msgs::msg::SlamPose>::SharedPtr slam_pose_pub_;
    rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr cam_info_sub_;
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;

    // ── Camera info ───────────────────────────────────────────
    void on_camera_info(const sensor_msgs::msg::CameraInfo::SharedPtr msg)
    {
        if (cam_calibrated_) return;
        K_ = cv::Mat(3, 3, CV_64F, const_cast<double*>(msg->k.data())).clone();
        dist_ = cv::Mat(1, 5, CV_64F, const_cast<double*>(msg->d.data())).clone();
        cam_calibrated_ = true;
        RCLCPP_INFO(get_logger(), "Camera calibration received. fx=%.1f fy=%.1f",
                    K_.at<double>(0,0), K_.at<double>(1,1));
    }

    // ── Image callback: feature extraction + tracking ─────────
    void on_image(const sensor_msgs::msg::Image::SharedPtr msg)
    {
        if (!cam_calibrated_) {
            RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000,
                                 "Waiting for camera calibration...");
            return;
        }

        // Convert to grayscale
        cv_bridge::CvImagePtr cv_img;
        try {
            cv_img = cv_bridge::toCvCopy(msg, "mono8");
        } catch (const cv_bridge::Exception& e) {
            RCLCPP_ERROR(get_logger(), "cv_bridge error: %s", e.what());
            return;
        }

        cv::Mat gray = cv_img->image;
        double ts = rclcpp::Time(msg->header.stamp).seconds();

        // Extract ORB features
        std::vector<cv::KeyPoint> kps;
        cv::Mat descs;
        orb_->detectAndCompute(gray, cv::noArray(), kps, descs);

        if ((int)kps.size() < min_features_) {
            // Too few features: degrade quality
            slam_quality_ *= 0.85;
            consecutive_good_ = 0;
            publish_slam_pose(msg->header.stamp, false);
            return;
        }

        TrackedFrame curr;
        curr.timestamp_s = ts;
        curr.keypoints   = kps;
        curr.descriptors = descs;
        curr.valid       = true;

        if (!slam_initialized_) {
            prev_frame_       = curr;
            prev_frame_.pose  = cv::Mat::eye(4, 4, CV_64F);
            slam_initialized_ = true;
            RCLCPP_INFO(get_logger(), "SLAM first frame captured. Features: %zu", kps.size());
            return;
        }

        // Match with previous frame
        std::vector<cv::DMatch> matches;
        if (!prev_frame_.descriptors.empty() && !descs.empty()) {
            matcher_->match(prev_frame_.descriptors, descs, matches);

            // Filter by distance
            double min_dist = 1e9;
            for (const auto& m : matches)
                min_dist = std::min(min_dist, (double)m.distance);
            std::vector<cv::DMatch> good_matches;
            for (const auto& m : matches)
                if (m.distance < std::max(2.0 * min_dist, 30.0))
                    good_matches.push_back(m);

            tracked_features_ = (int)good_matches.size();

            if (tracked_features_ >= min_features_) {
                // Estimate essential matrix
                std::vector<cv::Point2f> pts1, pts2;
                for (const auto& m : good_matches) {
                    pts1.push_back(prev_frame_.keypoints[m.queryIdx].pt);
                    pts2.push_back(curr.keypoints[m.trainIdx].pt);
                }

                cv::Mat mask;
                cv::Mat E = cv::findEssentialMat(pts1, pts2, K_,
                                                 cv::RANSAC, 0.999, 1.0, mask);
                cv::Mat R, t;
                if (!E.empty()) {
                    int inliers = cv::recoverPose(E, pts1, pts2, K_, R, t, mask);
                    if (inliers > min_features_ / 2) {
                        update_pose(R, t);
                        double inlier_ratio = (double)inliers / (double)good_matches.size();
                        slam_quality_ = 0.7 * slam_quality_ + 0.3 * inlier_ratio;
                        consecutive_good_++;
                    } else {
                        slam_quality_ *= 0.9;
                        consecutive_good_ = 0;
                    }
                }
            } else {
                slam_quality_ *= 0.85;
                consecutive_good_ = 0;
            }
        }

        curr.pose = pose_world_.clone();
        maintain_history(curr);
        prev_frame_ = curr;

        publish_slam_pose(msg->header.stamp, true);
    }

    // ── Update world pose from relative R,t ──────────────────
    void update_pose(const cv::Mat& R, const cv::Mat& t)
    {
        // Build 4x4 relative transform
        cv::Mat T = cv::Mat::eye(4, 4, CV_64F);
        R.copyTo(T(cv::Rect(0, 0, 3, 3)));
        t.copyTo(T(cv::Rect(3, 0, 1, 3)));

        // Accumulate pose (monocular: scale unobservable without fusion)
        pose_world_ = pose_world_ * T.inv();
    }

    // ── Maintain sliding window for drift detection ───────────
    void maintain_history(const TrackedFrame& frame)
    {
        frame_history_.push_back(frame);
        if (frame_history_.size() > HISTORY_SIZE)
            frame_history_.pop_front();
    }

    // ── Publish SLAM pose ─────────────────────────────────────
    void publish_slam_pose(const rclcpp::Time& stamp, bool valid)
    {
        auto msg = phantom_msgs::msg::SlamPose();
        msg.header.stamp    = stamp;
        msg.header.frame_id = "slam_world";

        if (valid && !pose_world_.empty()) {
            msg.x = pose_world_.at<double>(0, 3);
            msg.y = pose_world_.at<double>(1, 3);
            msg.z = pose_world_.at<double>(2, 3);

            // Extract rotation as quaternion
            cv::Mat R = pose_world_(cv::Rect(0, 0, 3, 3));
            double trace = R.at<double>(0,0) + R.at<double>(1,1) + R.at<double>(2,2);
            double qw = std::sqrt(std::max(0.0, 1.0 + trace)) * 0.5;
            double qx = std::sqrt(std::max(0.0, 1.0 + R.at<double>(0,0) - R.at<double>(1,1) - R.at<double>(2,2))) * 0.5;
            double qy = std::sqrt(std::max(0.0, 1.0 - R.at<double>(0,0) + R.at<double>(1,1) - R.at<double>(2,2))) * 0.5;
            double qz = std::sqrt(std::max(0.0, 1.0 - R.at<double>(0,0) - R.at<double>(1,1) + R.at<double>(2,2))) * 0.5;
            msg.qw = qw; msg.qx = qx; msg.qy = qy; msg.qz = qz;
        }

        msg.quality              = (float)std::clamp(slam_quality_, 0.0, 1.0);
        msg.tracked_features     = tracked_features_;
        msg.loop_closure_active  = loop_closure_active_;
        msg.slam_initialized     = slam_initialized_;

        // Simplified covariance (inversely proportional to quality)
        double pos_var = (slam_quality_ > 0.1) ? (1.0 / slam_quality_) : 10.0;
        for (int i = 0; i < 36; i++) msg.covariance[i] = 0.0;
        msg.covariance[0]  = pos_var;
        msg.covariance[7]  = pos_var;
        msg.covariance[14] = pos_var;
        msg.covariance[21] = 0.1;
        msg.covariance[28] = 0.1;
        msg.covariance[35] = 0.1;

        slam_pose_pub_->publish(msg);
    }
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PhantomVisionNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
