#!/usr/bin/env python3
"""
PhantomNav™ — Complete Edge Stack Launch File
Launches all 6 edge modules in dependency order.

Usage:
  ros2 launch phantomnav phantomnav_edge.launch.py
  ros2 launch phantomnav phantomnav_edge.launch.py sim:=true
  ros2 launch phantomnav phantomnav_edge.launch.py log_level:=debug
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():

    # ── Arguments ──────────────────────────────────────────────
    sim_arg = DeclareLaunchArgument(
        'sim', default_value='false',
        description='Launch simulation node alongside edge stack')
    log_level_arg = DeclareLaunchArgument(
        'log_level', default_value='info',
        description='ROS 2 log level: debug | info | warn | error')
    drone_id_arg = DeclareLaunchArgument(
        'drone_id', default_value='drone-001',
        description='Unique drone identifier for MQTT topics')

    params_file = PathJoinSubstitution([
        FindPackageShare('phantomnav'),
        'config', 'edge', 'params.yaml'
    ])

    log_level  = LaunchConfiguration('log_level')
    sim_mode   = LaunchConfiguration('sim')
    drone_id   = LaunchConfiguration('drone_id')

    # ── Phase 1: Core state estimation ────────────────────────
    phantom_core = Node(
        package='phantom_core',
        executable='phantom_core_node',
        name='phantom_core_node',
        output='screen',
        parameters=[params_file],
        arguments=['--ros-args', '--log-level', log_level],
        remappings=[
            ('/imu/data',     '/imu/data'),
            ('/gnss/fix',     '/gnss/fix'),
            ('/gnss/velocity','/gnss/velocity'),
        ],
    )

    # ── Phase 2: SLAM (delayed 1s to allow core init) ─────────
    phantom_vision = TimerAction(
        period=1.0,
        actions=[Node(
            package='phantom_vision',
            executable='phantom_vision_node',
            name='phantom_vision_node',
            output='screen',
            parameters=[params_file],
            arguments=['--ros-args', '--log-level', log_level],
        )]
    )

    # ── Phase 3: Fusion (delayed 2s) ──────────────────────────
    phantom_fusion = TimerAction(
        period=2.0,
        actions=[Node(
            package='phantom_fusion',
            executable='phantom_fusion_node',
            name='phantom_fusion_node',
            output='screen',
            parameters=[params_file],
            arguments=['--ros-args', '--log-level', log_level],
        )]
    )

    # ── Phase 4: Confidence + Decision (delayed 3s) ───────────
    phantom_sense = TimerAction(
        period=3.0,
        actions=[Node(
            package='phantom_sense',
            executable='confidence_node',
            name='phantom_sense_node',
            output='screen',
            parameters=[params_file],
            arguments=['--ros-args', '--log-level', log_level],
        )]
    )

    phantom_decision = TimerAction(
        period=3.5,
        actions=[Node(
            package='phantom_decision',
            executable='decision_node',
            name='phantom_decision_node',
            output='screen',
            parameters=[params_file],
            arguments=['--ros-args', '--log-level', log_level],
        )]
    )

    # ── Phase 5: Cloud gateway (delayed 5s) ───────────────────
    phantom_interface = TimerAction(
        period=5.0,
        actions=[Node(
            package='phantom_interface',
            executable='gateway_node',
            name='phantom_interface_node',
            output='screen',
            parameters=[
                params_file,
                {'drone_id': drone_id},
            ],
            arguments=['--ros-args', '--log-level', log_level],
        )]
    )

    # ── Optional: Simulation node ──────────────────────────────
    sim_node = Node(
        package='phantom_simulation',
        executable='gnss_denied_sim',
        name='phantom_sim_node',
        output='screen',
        condition=IfCondition(sim_mode),
        parameters=[{'drone_id': drone_id}],
    )

    # ── Startup banner ─────────────────────────────────────────
    banner = LogInfo(msg=[
        '\n',
        '╔══════════════════════════════════════════════════╗\n',
        '║         PhantomNav™ Edge Stack Starting           ║\n',
        '║  PhantomCore  → PhantomVision → PhantomFusion    ║\n',
        '║  PhantomSense → PhantomDecision → PhantomInterface║\n',
        '╚══════════════════════════════════════════════════╝',
    ])

    return LaunchDescription([
        sim_arg,
        log_level_arg,
        drone_id_arg,
        banner,
        phantom_core,
        phantom_vision,
        phantom_fusion,
        phantom_sense,
        phantom_decision,
        phantom_interface,
        sim_node,
    ])
