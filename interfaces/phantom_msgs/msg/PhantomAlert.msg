std_msgs/Header header

uint8 severity    # 0=INFO 1=WARNING 2=ERROR 3=CRITICAL
string source     # Module that raised the alert
string code       # Machine-readable code
string message    # Human-readable description

# Relevant telemetry snapshot at alert time
float32 confidence_at_alert
uint8 nav_mode_at_alert
