std_msgs/Header header

# Position (meters, NED frame)
float64 x
float64 y
float64 z

# Velocity (m/s)
float64 vx
float64 vy
float64 vz

# Orientation (quaternion)
float64 qw
float64 qx
float64 qy
float64 qz

# Covariance (6x6 flattened: x y z roll pitch yaw)
float64[36] covariance

# GNSS status
bool gnss_valid
float64 gnss_accuracy_m
