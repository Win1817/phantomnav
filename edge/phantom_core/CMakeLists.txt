cmake_minimum_required(VERSION 3.8)
project(phantom_core)

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-O2 -Wall -Wextra)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(phantom_msgs REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)

# ── EKF shared library ─────────────────────────────────────────
add_library(phantom_ekf SHARED
  src/ekf.cpp
)
target_include_directories(phantom_ekf PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(phantom_ekf
  Eigen3::Eigen
)
ament_target_dependencies(phantom_ekf
  rclcpp
)

# ── PhantomCore node executable ───────────────────────────────
add_executable(phantom_core_node
  src/phantom_core_node.cpp
)
target_include_directories(phantom_core_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(phantom_core_node
  phantom_ekf
  Eigen3::Eigen
)
ament_target_dependencies(phantom_core_node
  rclcpp
  sensor_msgs
  geometry_msgs
  std_msgs
  phantom_msgs
)

install(TARGETS phantom_core_node phantom_ekf
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY include/
  DESTINATION include)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL)

ament_export_libraries(phantom_ekf)
ament_export_include_directories(include)
ament_package()
