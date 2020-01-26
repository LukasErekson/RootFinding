""" Generate Test polynomials and run our solver using those random, bivariate
    polynomials. Also, output each polynomial used to a Matlab-readable file
    so that we can run the tests on Chebfun as well.
"""

import yroots as yr
import numpy as np 
from poly_str import poly_str
from yroots.polynomial import getPoly
import time
from matplotlib import pyplot as plt

def timeIt(funcs, a=np.array([-1,-1]), b=np.array([1,1]), trials=5):
    """ Runs the test multiple times and takes the average of the times.

    Parameters
    ----------
        funcs : lambda functions
            The functions to run the tests on.
        a : np.array
            Lower bounds of the interval.
        b : np.array
            Upper bounds of the interval.
        trials : int
            Number of times to run the tests.

    Returns
    -------
        time : float
            The average time per trial it took.
    """
    time_list = list()
    for i in range(trials):
        start = time.time()
        roots = yr.solve(funcs, a, b)
        end = time.time()
        time_list.append(end - start)
    # print(time_list)

    return sum(time_list)/trials

def poly_str(poly, output='matlab'):
    """Takes in a polynomial and prints out in a format that matlab can read.
    
    Parameters
    ----------
        poly : Polynomial object
            Polynomial in power form to output.
    
    Returns
    ----------
        poly_string : str
            Polynomial in a format that matlab can read.
    """
    deg = poly.degree
    poly_string = str()
    if output == 'matlab':
        for i in range(deg + 1): #Powers of y
            for j in range(deg + 1 - i): # Powers of x
                poly_string += " + (" + str(poly.coeff[j][i])
                if (j > 0):
                    poly_string += ".*(x.^" + str(j) + ")"
                if (i > 0):
                    poly_string += ".*(y.^" + str(i) + ")"
                poly_string += ")"
    elif output == 'latex':
        for i in range(deg + 1): #Powers of y
            for j in range(deg + 1 - i): # Powers of x
                poly_string += " + (" + str(poly.coeff[j][i])
                if (j > 0):
                    poly_string += "(x^{" + str(j) + "})"
                if (i > 0):
                    poly_string += "(y^{" + str(i) + "})"
                poly_string += ")"
    elif output == 'python':
        for i in range(deg + 1): #Powers of y
            for j in range(deg + 1 - i): # Powers of x
                poly_string += " + (" + str(poly.coeff[j][i])
                if (j > 0):
                    poly_string += "*(x**" + str(j) + ")"
                if (i > 0):
                    poly_string += "*(y**" + str(i) + ")"
                poly_string += ")"
    else:
        raise ValueError("The accepted outputs are matlab, latex, and python.")
    return poly_string[3:] # Take out the begining " + " from the final string.


def generate_tests(degree, num_trials):
    """ Generates tests starting from degree 5 and going to a specified degree
        and averages the times it takes to solve num_trials systems of bivariate
        polynomials.
    """
    degrees = [i for i in range(5, degree + 5, 5)]
    # np.random.seed(0)
    YRoots_times = list()
    for deg in degrees:
        deg_time = 0
        with open('chebfun_polys.m', 'a') as fi:
            fi.write("disp('=============================================')\n")
            fi.write("disp('Degree " + str(deg) + "')\n \n")
            fi.write('deg_time = 0;\n\n')
        for trial in range(num_trials):
            # Ensure a unique random poly
            np.random.seed(deg + trial)
            f = getPoly(deg, 2, True)
            g = getPoly(deg, 2, True)

            lf = lambda x, y: eval(poly_str(f, 'python'))
            lg = lambda x, y: eval(poly_str(g, 'python'))

            deg_time += timeIt([lf, lg])

            with open('chebfun_polys.m', 'a') as fi:
                fi.write('f = @(x,y) ' + poly_str(f, 'matlab') + ';\n')
                fi.write('g = @(x,y) ' + poly_str(g, 'matlab') + ';\n')
                fi.write('deg_time = deg_time + timeIt(f,g);' + ';\n\n')
        YRoots_times.append(deg_time/num_trials)

        with open('chebfun_polys.m', 'a') as fi:
            fi.write("disp('Average time:')\n")
            fi.write("disp(deg_time./ " + str(num_trials) + ")\n\n")

    with open('YRoots v. Chebfun.txt','a') as fi:
        fi.write('Degree 5 - ' + str(degree) + '\n')
        fi.write(str(YRoots_times))
    return YRoots_times


def test_lambdas(): 
    """ Test the timing of evaluating lambda functions against evaluations of
        polynomial class objects. This could be a reason for potential slow-down. 
    """
    # Testing lambda evaluations vs our callable evaluations
    lamb_times = list()
    class_times = list()
    num_trials = 3
    degrees = [i for i in range(5, 25, 5)]

    # Test random bivariate polynomials of varying degree
    # Fix a random seed
    for deg in degrees:
        c_time = 0
        l_time = 0
        for trial in range(num_trials):
            f = getPoly(deg, 2, True)
            g = getPoly(deg, 2, True)

            f_lamb = lambda x,y: eval(poly_str(f, 'python'))
            g_lamb = lambda x,y: eval(poly_str(g, 'python'))
            
            c_time += timeIt([f,g])
            l_time += timeIt([f_lamb, g_lamb])
            
        class_times.append(c_time/num_trials)
        lamb_times.append(l_time/num_trials)


    plt.title("Class Evaluations v.s Lambda Evaulations")
    plt.plot(degrees, class_times, label='Class eval times')
    plt.plot(degrees, lamb_times, label='Lambda eval times')
    plt.xlabel('Degree')
    plt.ylabel('Solve Time (s)')
    plt.legend()
    plt.show()

    print(class_times)
    print(lamb_times)