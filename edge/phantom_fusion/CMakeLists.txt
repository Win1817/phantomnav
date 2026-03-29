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

add_executable(phantom_fusion_node
  src/phantom_fusion_node.cpp
)
target_include_directories(phantom_fusion_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(phantom_fusion_node
  Eigen3::Eigen
)
ament_target_dependencies(phantom_fusion_node
  rclcpp
  std_msgs
  phantom_msgs
)

install(TARGETS phantom_fusion_node
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include
  OPTIONAL)

ament_package()
