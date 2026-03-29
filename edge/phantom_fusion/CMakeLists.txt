cmake_minimum_required(VERSION 3.8)
project(phantom_fusion)

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-O2 -Wall -Wextra)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(phantom_msgs REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)

include_directories(
  include
  ${EIGEN3_INCLUDE_DIRS}
)

add_executable(phantom_fusion_node
  src/phantom_fusion_node.cpp
)

ament_target_dependencies(phantom_fusion_node
  rclcpp
  std_msgs
  phantom_msgs
  Eigen3
  eigen3_cmake_module
)

install(TARGETS phantom_fusion_node
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include
  OPTIONAL)

ament_package()
