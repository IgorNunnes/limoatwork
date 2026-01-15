from setuptools import setup
import os
from glob import glob

package_name = 'limo_bringup'

setup(
    name=package_name,
    version='0.0.0',
    packages=[],  # bringup: sin módulos Python
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
         glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='atwork',
    maintainer_email='you@example.com',
    description='LIMO bringup package for ROS 2 Jazzy',
    license='Apache License 2.0',
)

