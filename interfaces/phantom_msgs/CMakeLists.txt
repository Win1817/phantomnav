cmake_minimum_required(VERSION 3.8)
project(phantom_msgs)

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/StateEstimate.msg"
  "msg/SlamPose.msg"
  "msg/FusedPose.msg"
  "msg/ConfidenceScore.msg"
  "msg/NavMode.msg"
  "msg/PhantomAlert.msg"
  DEPENDENCIES std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
