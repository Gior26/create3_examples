# Copyright 2021 iRobot Corporation. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from irobot_create_msgs.msg import LedColor
from irobot_create_msgs.msg import LightringLeds

class ColorPalette():
    """ Helper Class to define frequently used colors"""
    def __init__(self):
        self.red = LedColor(red=255,green=0,blue=0)
        self.green = LedColor(red=0,green=255,blue=0)
        self.blue = LedColor(red=0,green=0,blue=255)
        self.yellow = LedColor(red=255,green=255,blue=0)
        self.pink = LedColor(red=255,green=0,blue=255)
        self.cyan = LedColor(red=0,green=255,blue=255)
        self.purple = LedColor(red=127,green=0,blue=255)
        self.white = LedColor(red=255,green=255,blue=255)
        self.grey = LedColor(red=189,green=189,blue=189)

class Move():
    """ Class to tell the robot to move as part of dance sequence"""
    def __init__(self, x_m_s, theta_degrees_second):
        """
        Parameters
        ----------
        x_m_s : float
            The speed to drive the robot forward (positive) /backwards (negative) in m/s    
        theta_degrees_second : float
            The speed to rotate the robot counter clockwise (positive) / clockwise (negative) in deg/s
        """
        self.x = x_m_s
        self.theta = math.radians(theta_degrees_second)

class Lights():
    """ Class to tell the robot to set lightring lights as part of dance sequence"""
    def __init__(self, led_colors):
        """
        Parameters
        ----------
        led_colors : list of LedColor
            The list of 6 LedColors corresponding to the 6 LED lights on the lightring
        """
        self.led_colors = led_colors

class FinishedDance():
    """ Class to tell the robot dance sequence has finished"""
    pass

class DanceChoreographer():
    """ Class to manage a dance sequence, returning current actions to perform"""
    def __init__(self, dance_sequence):
        '''
        Parameters
        ----------
        dance_sequence : list of (time, action) pairs
            The time is time since start_dance was called to initiate action,
            the action is one of the classes above [Move,Lights,FinishedDance]
        '''    
        self.dance_sequence = dance_sequence
        self.action_index = 0

    def start_dance(self, time):
        '''
        Parameters
        ----------
        time : rclpy::Time
            The ROS 2 time to mark the start of the sequence
        '''    
        self.start_time = time
        self.action_index = 0

    def get_next_actions(self, time):
        '''
        Parameters
        ----------
        time : rclpy::Time
            The ROS 2 time to compare against start time to give actions that should be applied given how much time sequence has been running for
        '''    
        time_into_dance = time - self.start_time
        time_into_dance_seconds = time_into_dance.nanoseconds / float(1e9)
        actions = []
        while self.action_index < len(self.dance_sequence) and time_into_dance_seconds >= self.dance_sequence[self.action_index][0]:
            actions.append(self.dance_sequence[self.action_index][1])
            self.action_index += 1
        return actions

class DanceCommandPublisher(Node):
    """ Class to publish actions produced by the DanceChoreographer"""
    def __init__(self, dance_choreographer):
        '''
        Parameters
        ----------
        dance_choreographer : DanceChoreographer
            The configured DanceChoreographer to give time and query for actions to publish
        '''    
        super().__init__('dance_command_publisher')
        self.dance_choreographer = dance_choreographer
        self.lights_publisher = self.create_publisher(LightringLeds, 'cmd_lightring', 10)
        self.vel_publisher = self.create_publisher(Twist, 'cmd_vel', 10)
        timer_period = 0.05  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        self.last_twist = Twist()
        self.last_lightring = LightringLeds()
        self.last_lightring.override_system = False
        self.ready = False
        self.last_wait_subscriber_printout = None

    def timer_callback(self):
        current_time = self.get_clock().now()
        # Set lights >= until populated in sim
        if not self.ready:
            if self.vel_publisher.get_subscription_count() > 0 and self.lights_publisher.get_subscription_count() >= 0:
                self.get_logger().info('Subscribers connected, start dance at time %f' % (current_time.nanoseconds / float(1e9)))
                self.ready = True
                self.dance_choreographer.start_dance(current_time)
            elif not self.last_wait_subscriber_printout or ((current_time - self.last_wait_subscriber_printout).nanoseconds / float(1e9)) > 5.0:
                # Only print once every 5 seconds
                self.last_wait_subscriber_printout = current_time
                self.get_logger().info('Waiting for publishers to connect to subscribers')
                return
            else:
                return
        next_actions = self.dance_choreographer.get_next_actions(current_time)
        twist = self.last_twist
        lightring = self.last_lightring
        for next_action in next_actions:
            if isinstance(next_action, Move):
                twist = Twist()
                twist.linear.x = next_action.x
                twist.angular.z = next_action.theta
                self.last_twist = twist
                self.get_logger().info('Time %f New move action: %f, %f' % (current_time.nanoseconds / float(1e9), twist.linear.x, twist.angular.z))
            elif isinstance(next_action, Lights):
                lightring = LightringLeds()
                lightring.override_system = True
                lightring.leds = next_action.led_colors
                self.last_lightring = lightring
                self.get_logger().info('Time %f New lights action, first led (%d,%d,%d)' % (current_time.nanoseconds / float(1e9), lightring.leds[0].red, lightring.leds[0].green, lightring.leds[0].blue))
            else:
                twist = Twist()
                twist.linear.x = 0.0
                twist.angular.z = 0.0
                self.last_twist = twist
                lightring = LightringLeds()
                lightring.override_system = False
                self.last_lightring = lightring
                self.get_logger().info('Time %f Finished Dance Sequence' % (current_time.nanoseconds / float(1e9)))

        lightring.header.stamp = current_time.to_msg()
        self.vel_publisher.publish(twist)
        self.lights_publisher.publish(lightring)