std_msgs/Header header

# Pose in camera/world frame
float64 x
float64 y
float64 z
float64 qw
float64 qx
float64 qy
float64 qz

# SLAM health metrics
float64 quality         # 0.0 - 1.0
int32 tracked_features
bool loop_closure_active
bool slam_initialized

# Pose covariance (6x6 flattened)
float64[36] covariance
