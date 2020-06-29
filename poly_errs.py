from yroots.polynomial import MultiPower
import pickle
import yroots as yr
import numpy as np
import time

a = -np.ones(2)
b = np.ones(2)
num_loops = 1
num_tests = 20
start_deg = 2
larger_deg = 40
deg_skip = 1

for deg in range(start_deg, larger_deg + 1, deg_skip):
    coeffs = np.load("tests/bivariate_poly_tests/dim2_deg{}_randn.npy".format(deg))
    
    deg_time = 0
    for test in range(num_tests):
        
        c1 = coeffs[test, 0, :, :]
        c2 = coeffs[test, 1, :, :]

        f = MultiPower(c1)
        g = MultiPower(c2)
        
        yr.solve([f,g], a, b, plot_name="Random Degree {} Bivariate Polys".format(deg),
                 plot_err=test==num_tests-1, max_level=9)# or test%5 == 4)
        
        del c1, c2, f, g
        
    del coeffs
    yr.subdivision.approx_err_dict = {i:[] for i in range(16)}
    yr.subdivision.trim_err_dict = {i:[] for i in range(16)}
    yr.subdivision.good_degs_dict = {i:[] for i in range(16)}