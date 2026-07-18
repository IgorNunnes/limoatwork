from setuptools import setup

package_name = 'mycobot_apriltag_tracking'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='limopro',
    maintainer_email='limopro@todo.todo',
    description='Pose sequence publisher for mycobot 280',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pose_sequence_publisher = mycobot_apriltag_tracking.pose_sequence_publisher:main',
            'mycobot_pose_controller = mycobot_apriltag_tracking.mycobot_pose_controller:main',
        ],
    },
)
