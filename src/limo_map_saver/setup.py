from setuptools import setup

package_name = 'limo_map_saver'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name, 'scripts'], # Adicione a pasta 'scripts'
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='solverbot',
    maintainer_email='solverbot@todo.todo',
    description='Nó que ouve o gatilho do joystick para salvar o mapa',
    license='Apache-2.0',
    tests_require=['pytest'],

    # --- ESTA É A PARTE MAIS IMPORTANTE ---
    entry_points={
        'console_scripts': [
            'map_saver_listener = scripts.map_saver_listener:main',
        ],
    },
)
