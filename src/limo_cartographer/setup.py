from setuptools import setup
import os
from glob import glob

package_name = 'limo_cartographer'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        # ament index
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # package.xml
        ('share/' + package_name, ['package.xml']),
        # launch files
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        # config files
        (os.path.join('share', package_name, 'config'),
            glob('config/*.lua')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='atwork',
    maintainer_email='atwork@todo.todo',
    description='Cartographer configuration for AgileX LIMO',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [],
    },
)
