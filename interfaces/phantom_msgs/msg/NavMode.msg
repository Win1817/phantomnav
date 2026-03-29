std_msgs/Header header

# Navigation mode
# 0 = GNSS_PRIMARY
# 1 = INS_SLAM_FUSION
# 2 = INS_ONLY
# 3 = SAFE_MODE
# 4 = EMERGENCY_HOLD
uint8 mode
string mode_name

# Transition metadata
string reason
float32 confidence_at_switch
bool gnss_available
bool slam_available

# Mode constants
uint8 GNSS_PRIMARY     = 0
uint8 INS_SLAM_FUSION  = 1
uint8 INS_ONLY         = 2
uint8 SAFE_MODE        = 3
uint8 EMERGENCY_HOLD   = 4
