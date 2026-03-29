#pragma once

#include <Eigen/Dense>
#include <rclcpp/rclcpp.hpp>
#include <array>

namespace phantom_core {

// State vector: [x, y, z, vx, vy, vz, qw, qx, qy, qz, bax, bay, baz, bgx, bgy, bgz]
// x,y,z     : position (NED, meters)
// vx,vy,vz  : velocity (m/s)
// qw..qz    : orientation quaternion
// bax..baz  : accelerometer bias
// bgx..bgz  : gyroscope bias
constexpr int STATE_DIM = 16;
constexpr int MEAS_GNSS_DIM = 6;   // pos + vel
constexpr int MEAS_IMU_DIM  = 6;   // accel + gyro

using StateVec  = Eigen::Matrix<double, STATE_DIM, 1>;
using StateMat  = Eigen::Matrix<double, STATE_DIM, STATE_DIM>;
using GnssMeas  = Eigen::Matrix<double, MEAS_GNSS_DIM, 1>;
using GnssMat   = Eigen::Matrix<double, MEAS_GNSS_DIM, STATE_DIM>;
using CovMat    = Eigen::Matrix<double, STATE_DIM, STATE_DIM>;

struct ImuMeasurement {
    double ax, ay, az;           // Accelerometer (m/s^2)
    double gx, gy, gz;           // Gyroscope (rad/s)
    double timestamp_s;
};

struct GnssMeasurement {
    double x, y, z;              // Position (NED, meters)
    double vx, vy, vz;           // Velocity (m/s)
    double pos_accuracy_m;
    double vel_accuracy_ms;
    bool valid;
    double timestamp_s;
};

struct EkfState {
    StateVec x;      // State estimate
    CovMat   P;      // Error covariance
    double   timestamp_s;
    bool     initialized;
};

class ExtendedKalmanFilter {
public:
    ExtendedKalmanFilter();

    // Initialize state from first GNSS fix
    void initialize(const GnssMeasurement& gnss_meas);

    // Predict step: propagate state using IMU integration
    void predict(const ImuMeasurement& imu);

    // Update step: correct state with GNSS measurement
    void update_gnss(const GnssMeasurement& gnss);

    // Get current state estimate
    const EkfState& state() const { return state_; }

    // Get position covariance (3x3 sub-block)
    Eigen::Matrix3d position_covariance() const;

    // Get full 6x6 pose covariance (pos + orient)
    Eigen::Matrix<double, 6, 6> pose_covariance() const;

    // Noise tuning
    void set_process_noise(double accel_noise, double gyro_noise,
                           double accel_bias_noise, double gyro_bias_noise);
    void set_gnss_noise(double pos_noise_m, double vel_noise_ms);

private:
    EkfState state_;

    // Process noise covariance
    StateMat Q_;

    // GNSS measurement noise
    Eigen::Matrix<double, MEAS_GNSS_DIM, MEAS_GNSS_DIM> R_gnss_;

    // Gravity vector (NED)
    Eigen::Vector3d gravity_;

    double last_imu_time_s_;
    bool first_imu_;

    // Quaternion helpers
    static Eigen::Quaterniond quaternion_from_state(const StateVec& x);
    static void normalize_quaternion(StateVec& x);
    static Eigen::Matrix3d quat_to_rotation(const Eigen::Quaterniond& q);
    static Eigen::Matrix<double, 4, 3> quaternion_kinematics_matrix(
        const Eigen::Quaterniond& q);

    // Jacobian of process model wrt state
    StateMat compute_F(const ImuMeasurement& imu, double dt,
                       const Eigen::Quaterniond& q,
                       const Eigen::Vector3d& accel_body);

    // GNSS measurement Jacobian
    GnssMat compute_H_gnss() const;
};

} // namespace phantom_core
