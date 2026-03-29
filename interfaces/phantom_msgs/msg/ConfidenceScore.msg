std_msgs/Header header

# Overall confidence (0 - 100)
float32 score

# Sub-scores (0.0 - 1.0)
float32 sensor_stability
float32 slam_quality
float32 drift_penalty
float32 gnss_factor

# Classification
string level   # NOMINAL | DEGRADED | CRITICAL | UNSAFE

# Raw metric snapshot
float32 imu_variance
float32 accel_norm_variance
float32 slam_feature_count_norm
