std_msgs/Header header

# Fused position (NED, meters)
float64 x
float64 y
float64 z

# Fused velocity (m/s)
float64 vx
float64 vy
float64 vz

# Fused orientation (quaternion)
float64 qw
float64 qx
float64 qy
float64 qz

# Fusion weights
float64 w_ins    # Weight on INS estimate
float64 w_slam   # Weight on SLAM estimate

# Accumulated drift estimate (m)
float64 drift_estimate_m

# Fused covariance (6x6 flattened)
float64[36] covariance
