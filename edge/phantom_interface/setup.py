from setuptools import find_packages, setup

package_name = 'phantom_interface'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'paho-mqtt'],
    zip_safe=True,
    maintainer='PhantomOrg Engineering',
    maintainer_email='eng@phantomorg.dev',
    description='PhantomInterface™ — Async MQTT edge-to-cloud gateway',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gateway_node = phantom_interface.gateway_node:main',
        ],
    },
)
