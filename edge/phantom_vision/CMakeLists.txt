cmake_minimum_required(VERSION 3.8)
project(phantom_vision)

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-O2 -Wall -Wextra)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(phantom_msgs REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core features2d calib3d imgproc)

include_directories(
  include
  ${OpenCV_INCLUDE_DIRS}
)

add_executable(phantom_vision_node
  src/phantom_vision_node.cpp
)

target_link_libraries(phantom_vision_node
  ${OpenCV_LIBS}
)

ament_target_dependencies(phantom_vision_node
  rclcpp
  sensor_msgs
  std_msgs
  cv_bridge
  image_transport
  phantom_msgs
)

install(TARGETS phantom_vision_node
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include
  OPTIONAL)

ament_package()
