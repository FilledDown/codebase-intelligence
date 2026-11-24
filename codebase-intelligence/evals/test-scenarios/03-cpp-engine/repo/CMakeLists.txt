cmake_minimum_required(VERSION 3.16)
project(game CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(game src/main.cpp src/engine.cpp src/renderer.cpp)
target_include_directories(game PRIVATE include)

add_executable(test_vec2 tests/test_vec2.cpp)
target_include_directories(test_vec2 PRIVATE include)
