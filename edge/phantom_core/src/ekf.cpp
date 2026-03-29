#include "phantom_core/ekf.hpp"
#include <cmath>
#include <stdexcept>

namespace phantom_core {

// ─────────────────────────────────────────────────────────────
// Constructor: set default noise parameters
// ─────────────────────────────────────────────────────────────
ExtendedKalmanFilter::ExtendedKalmanFilter()
    : last_imu_time_s_(0.0), first_imu_(true)
{
    state_.x = StateVec::Zero();
    state_.x(6) = 1.0;    // qw = 1 (identity quaternion)
    state_.P = StateMat::Identity() * 1e-3;
    state_.initialized = false;

    gravity_ = Eigen::Vector3d(0.0, 0.0, 9.80665);   // NED: +z is down

    // Default process noise
    set_process_noise(0.1, 0.01, 1e-4, 1e-5);

    // Default GNSS measurement noise
    set_gnss_noise(2.0, 0.1);
}

// ─────────────────────────────────────────────────────────────
// Initialize from first GNSS fix
// ─────────────────────────────────────────────────────────────
void ExtendedKalmanFilter::initialize(const GnssMeasurement& gnss)
{
    if (!gnss.valid) return;

    state_.x = StateVec::Zero();
    state_.x(0) = gnss.x;
    state_.x(1) = gnss.y;
    state_.x(2) = gnss.z;
    state_.x(3) = gnss.vx;
    state_.x(4) = gnss.vy;
    state_.x(5) = gnss.vz;
    state_.x(6) = 1.0;    // qw

    // Initial covariance: generous position uncertainty
    state_.P = StateMat::Identity() * 1.0;
    state_.P(0,0) = state_.P(1,1) = state_.P(2,2) =
        gnss.pos_accuracy_m * gnss.pos_accuracy_m;

    state_.timestamp_s = gnss.timestamp_s;
    state_.initialized  = true;
    last_imu_time_s_    = gnss.timestamp_s;
}

// ─────────────────────────────────────────────────────────────
// Noise configurators
// ─────────────────────────────────────────────────────────────
void ExtendedKalmanFilter::set_process_noise(double accel_noise,
                                              double gyro_noise,
                                              double accel_bias_noise,
                                              double gyro_bias_noise)
{
    Q_ = StateMat::Zero();
    // Position — driven by velocity uncertainty
    Q_.block<3,3>(0,0) = Eigen::Matrix3d::Identity() * 1e-6;
    // Velocity — accelerometer noise
    Q_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * (accel_noise * accel_noise);
    // Quaternion — gyroscope noise
    Q_.block<4,4>(6,6) = Eigen::Matrix4d::Identity() * (gyro_noise * gyro_noise * 0.25);
    // Accelerometer bias random walk
    Q_.block<3,3>(10,10) = Eigen::Matrix3d::Identity() * (accel_bias_noise * accel_bias_noise);
    // Gyroscope bias random walk
    Q_.block<3,3>(13,13) = Eigen::Matrix3d::Identity() * (gyro_bias_noise * gyro_bias_noise);
}

void ExtendedKalmanFilter::set_gnss_noise(double pos_noise_m, double vel_noise_ms)
{
    R_gnss_ = Eigen::Matrix<double, MEAS_GNSS_DIM, MEAS_GNSS_DIM>::Zero();
    R_gnss_.block<3,3>(0,0) = Eigen::Matrix3d::Identity() * (pos_noise_m   * pos_noise_m);
    R_gnss_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * (vel_noise_ms  * vel_noise_ms);
}

// ─────────────────────────────────────────────────────────────
// Quaternion helpers
// ─────────────────────────────────────────────────────────────
Eigen::Quaterniond ExtendedKalmanFilter::quaternion_from_state(const StateVec& x)
{
    return Eigen::Quaterniond(x(6), x(7), x(8), x(9)).normalized();
}

void ExtendedKalmanFilter::normalize_quaternion(StateVec& x)
{
    double norm = std::sqrt(x(6)*x(6) + x(7)*x(7) + x(8)*x(8) + x(9)*x(9));
    if (norm > 1e-10) {
        x(6) /= norm; x(7) /= norm; x(8) /= norm; x(9) /= norm;
    }
}

Eigen::Matrix3d ExtendedKalmanFilter::quat_to_rotation(const Eigen::Quaterniond& q)
{
    return q.toRotationMatrix();
}

// Omega matrix for quaternion kinematics: dq/dt = 0.5 * Omega * q
Eigen::Matrix<double, 4, 3>
ExtendedKalmanFilter::quaternion_kinematics_matrix(const Eigen::Quaterniond& q)
{
    double qw = q.w(), qx = q.x(), qy = q.y(), qz = q.z();
    Eigen::Matrix<double, 4, 3> Xi;
    Xi << -qx, -qy, -qz,
           qw, -qz,  qy,
           qz,  qw, -qx,
          -qy,  qx,  qw;
    return Xi * 0.5;
}

// ─────────────────────────────────────────────────────────────
// Process model Jacobian F
// ─────────────────────────────────────────────────────────────
ExtendedKalmanFilter::StateMat
ExtendedKalmanFilter::compute_F(const ImuMeasurement& imu, double dt,
                                 const Eigen::Quaterniond& q,
                                 const Eigen::Vector3d& accel_body)
{
    StateMat F = StateMat::Identity();
    Eigen::Matrix3d R = quat_to_rotation(q);

    // d(pos)/d(vel)
    F.block<3,3>(0,3) = Eigen::Matrix3d::Identity() * dt;

    // d(vel)/d(accel_bias) — rotation brings bias into world frame
    F.block<3,3>(3,10) = -R * dt;

    // Skew-symmetric of rotated acceleration for d(vel)/d(quat) cross terms
    Eigen::Vector3d a_world = R * accel_body;
    Eigen::Matrix3d a_skew;
    a_skew <<     0,  -a_world(2),  a_world(1),
             a_world(2),      0,  -a_world(0),
            -a_world(1),  a_world(0),      0;
    // Simplified: d(vel)/d(q) — approximate via skew * dt
    F.block<3,3>(3,6) = -a_skew * dt;

    // d(quat)/d(gyro_bias) — gyro bias affects quaternion kinematics
    Eigen::Matrix<double, 4, 3> Xi = quaternion_kinematics_matrix(q);
    F.block<4,3>(6,13) = -Xi * dt;

    return F;
}

// ─────────────────────────────────────────────────────────────
// GNSS measurement Jacobian H
// ─────────────────────────────────────────────────────────────
ExtendedKalmanFilter::GnssMat ExtendedKalmanFilter::compute_H_gnss() const
{
    GnssMat H = GnssMat::Zero();
    H.block<3,3>(0,0) = Eigen::Matrix3d::Identity();   // pos
    H.block<3,3>(3,3) = Eigen::Matrix3d::Identity();   // vel
    return H;
}

// ─────────────────────────────────────────────────────────────
// EKF Predict — IMU integration
// ─────────────────────────────────────────────────────────────
void ExtendedKalmanFilter::predict(const ImuMeasurement& imu)
{
    if (!state_.initialized) return;

    double dt = imu.timestamp_s - last_imu_time_s_;
    if (dt <= 0.0 || dt > 0.5) {
        last_imu_time_s_ = imu.timestamp_s;
        return;
    }
    last_imu_time_s_ = imu.timestamp_s;

    StateVec& x = state_.x;
    Eigen::Quaterniond q = quaternion_from_state(x);
    Eigen::Matrix3d R = quat_to_rotation(q);

    // Bias-corrected measurements
    Eigen::Vector3d accel(imu.ax - x(10), imu.ay - x(11), imu.az - x(12));
    Eigen::Vector3d omega(imu.gx - x(13), imu.gy - x(14), imu.gz - x(15));

    // ── State propagation ──────────────────────────────────────
    // Position: x += v*dt + 0.5*(R*a - g)*dt^2
    Eigen::Vector3d a_world = R * accel - gravity_;
    x.segment<3>(0) += x.segment<3>(3) * dt + 0.5 * a_world * dt * dt;

    // Velocity: v += (R*a - g)*dt
    x.segment<3>(3) += a_world * dt;

    // Quaternion: q += 0.5 * Xi * omega * dt
    Eigen::Matrix<double, 4, 3> Xi = quaternion_kinematics_matrix(q);
    x.segment<4>(6) += Xi * omega * dt;
    normalize_quaternion(x);

    // Biases: random walk (unchanged in nominal model)

    // ── Covariance propagation ─────────────────────────────────
    StateMat F = compute_F(imu, dt, q, accel);
    state_.P = F * state_.P * F.transpose() + Q_ * dt;

    // Enforce symmetry
    state_.P = 0.5 * (state_.P + state_.P.transpose());
    state_.timestamp_s = imu.timestamp_s;
}

// ─────────────────────────────────────────────────────────────
// EKF Update — GNSS correction
// ─────────────────────────────────────────────────────────────
void ExtendedKalmanFilter::update_gnss(const GnssMeasurement& gnss)
{
    if (!state_.initialized || !gnss.valid) return;

    // Adapt R based on GNSS-reported accuracy
    set_gnss_noise(gnss.pos_accuracy_m, gnss.vel_accuracy_ms);

    GnssMat H = compute_H_gnss();

    // Innovation: z - H*x
    GnssMeas z;
    z << gnss.x, gnss.y, gnss.z, gnss.vx, gnss.vy, gnss.vz;
    GnssMeas h_x;
    h_x << state_.x(0), state_.x(1), state_.x(2),
           state_.x(3), state_.x(4), state_.x(5);
    GnssMeas innov = z - h_x;

    // Innovation covariance: S = H*P*H' + R
    Eigen::Matrix<double, MEAS_GNSS_DIM, MEAS_GNSS_DIM> S =
        H * state_.P * H.transpose() + R_gnss_;

    // Kalman gain: K = P*H'*S^-1
    Eigen::Matrix<double, STATE_DIM, MEAS_GNSS_DIM> K =
        state_.P * H.transpose() * S.inverse();

    // State update
    state_.x += K * innov;
    normalize_quaternion(state_.x);

    // Covariance update (Joseph form for numerical stability)
    StateMat I_KH = StateMat::Identity() - K * H;
    state_.P = I_KH * state_.P * I_KH.transpose()
             + K * R_gnss_ * K.transpose();
    state_.P = 0.5 * (state_.P + state_.P.transpose());
    state_.timestamp_s = gnss.timestamp_s;
}

// ─────────────────────────────────────────────────────────────
// Covariance accessors
// ─────────────────────────────────────────────────────────────
Eigen::Matrix3d ExtendedKalmanFilter::position_covariance() const
{
    return state_.P.block<3,3>(0,0);
}

Eigen::Matrix<double, 6, 6> ExtendedKalmanFilter::pose_covariance() const
{
    Eigen::Matrix<double, 6, 6> cov;
    cov.block<3,3>(0,0) = state_.P.block<3,3>(0,0);  // pos
    cov.block<3,3>(3,3) = state_.P.block<3,3>(6,6);  // orient (quat approx)
    cov.block<3,3>(0,3).setZero();
    cov.block<3,3>(3,0).setZero();
    return cov;
}

} // namespace phantom_core
