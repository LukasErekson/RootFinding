"""
The check functions are all functions that take in a coefficent matrix and run a quick check
to determine if there can ever be zeros on the unit box there. They are then put into the list
all_bound_check_functions in the order we want to run them (probably fastest first). These are
then all run to throw out intervals as possible.
"""
import numpy as np
from itertools import product
import itertools
from yroots.polynomial import MultiCheb
from matplotlib import pyplot as plt
from yroots.polynomial import MultiCheb, Polynomial
from matplotlib import patches
from scipy import linalg as la
from math import fabs                      # faster than np.abs for small arrays
from yroots.utils import memoize

class IntervalData:
    '''
    Class to handle all the things related to intervals. It holds and runs the interval checks
    and also tracks what happened to each interval, and how much progress has been made.

    Attributes
    ----------
    interval_checks: list
        A list of functions. Each function accepts a coefficient matrix and a tolerance,
        and returns whether the Chebyshev Polynomial represented by that matrix, and
        accurate to within that tolerance, can ever be zero on the n dimensional interval [-1,1].
    subinterval_checks: list
        A list of functions. Each function accepts a coefficient matrix, a list of subintervals, a list of
        sign changes, and a tolerance. It then returns a list of booleans whether the Chebyshev Polynomial
        represented by that matrix, and accurate to within that tolerance, can ever be zero on the given subintervals.
        Before the checks can be run the subintervals must be rescaled to subintervals of [-1,1]
        The list of sign changes represents if we already know the function changes sign on a given subinterval.
    a: numpy array
        The lower bounds of the overall interval to solve on.
    b: numpy array
        The upper bounds of the overall interval to solve on.
    interval_results: dictionary
        A dictionary of funciton names to lists of intervals that were solved by that function.
    total_area: float
        The total n dimensional volume of the overall interval being solved on.
    current_area: float
        How much of the n dimensional volume has been checked.
    polishing: bool
        If true this class is just being used as a shell to pass into the polish code.
    polish_intervals: list
        The intervals polishing will be run on
    polish_num: int
        The number of time polishing has been run
    polish_interval_num: int
        The current interval being polished
    polish_a: numpy array
        The lower bounds of the interval being polished
    polish_b: numpy array
        The upper bounds of the interval being polished

    tick: int
        Keeps track of how many intervals have been solved. Every 100 it resets and prints the progress.

    Methods
    -------
    __init__
        Initializes everything.
    check_intervals
        Checks if a polynomial can be zero on an interval.
    check_subintervals
        Checks if a polynomial can be zero on an list of intervals.
    track_interval
        Tracks what happened to a given interval.
    print_progress
        Prints what percentage of the domain has been searched
    print_results
        Prints the results of how much each method contributed to the overall search
    plot_results
        Plots the results of subdivision solve
    '''
    def __init__(self,a,b):
        self.interval_checks = [constant_term_check]
        self.subinterval_checks = [quadratic_check]
        self.a = a
        self.b = b
        self.interval_results = dict()
        for check in self.interval_checks:
            self.interval_results[check.__name__] = []
        for check in self.subinterval_checks:
            self.interval_results[check.__name__] = []
        self.interval_results["Base Case"] = []
        self.interval_results["Macaulay"] = []
        self.interval_results["Too Deep"] = []
        self.total_area = np.prod(self.b-self.a)
        self.current_area = 0.
        self.tick = 0

        #For polishing code
        self.polishing = False
        self.polish_intervals = []
        self.polish_num = 0
        self.polish_interval_num = -1
        self.polish_a = np.array([])
        self.polish_b = np.array([])

        #for keeping track of condition numbers
        self.cond = 0
        self.backcond = 0

    def add_polish_intervals(self, polish_intervals):
        ''' Add the intervals that polishing will be run on.

        Parameters
        ----------
        polish_intervals : list
            The intervals polishing will be run on.
        '''
        self.polishing = True
        self.polish_intervals = polish_intervals
        self.polish_num += 1
        self.polish_interval_num = -1

    def start_polish_interval(self):
        '''Get the tracking ready to track the next polished interval
        '''
        #self.tick = 99 #So it will print right away.
        self.polish_interval_num += 1
        self.polish_a, self.polish_b = self.polish_intervals[self.polish_interval_num]
        self.total_area = np.prod(self.polish_b-self.polish_a)
        self.current_area = 0.

    def check_interval(self, coeff, error, a, b):
        ''' Runs the interval checks on the interval [a,b]

        Parameters
        ----------
        coeff : numpy array.
            The coefficient matrix of the Chebyshev approximation to check.
        error: float
            The approximation error.
        a: numpy array
            The lower bounds of the interval to check.
        b: numpy array
            The upper bounds of the interval to check.
        Returns
        -------
        check_interval : bool
            True if we can throw out the interval. Otherwise False.
        '''
        for check in self.interval_checks:
            if not check(coeff, error):
                if not self.polishing:
                    self.track_interval(check.__name__, [a,b])
                return True
        return False

    def check_subintervals(self, subintervals, scaled_subintervals, polys, errors):
        ''' Runs the subinterval checks on the given subintervals of [-1,1]

        Parameters
        ----------
        subintervals : list
            A list of the intervals to check.
        scaled_subintervals: list
            A list of the subintervals to check, scaled to be within the unit box that the approxiations are valid on.
        polys: list
            The coefficient tensors of Chebyshev polynomials that approximate the functions on these intervals..
        errors: list
            The approximation errors of the polynomials.
        Returns
        -------
        check_interval : bool
            True if we can throw out the interval. Otherwise False.
        '''
        for check in self.subinterval_checks:
            for poly,error in zip(polys, errors):
                mask = check(poly, scaled_subintervals, error)
                new_scaled_subintervals = []
                new_subintervals = []
                for i, result in enumerate(mask):
                    if result:
                        new_scaled_subintervals.append(scaled_subintervals[i])
                        new_subintervals.append(subintervals[i])
                    else:
                        if not self.polishing:
                            self.track_interval(check.__name__, subintervals[i])
                scaled_subintervals = new_scaled_subintervals
                subintervals = new_subintervals
        return subintervals

    def track_interval(self, name, interval):
        ''' Stores what happened to a given interval

        Parameters
        ----------
        name : string
            The name of the check or process (Macaulay, Base Case, Too Deep) that solved this interval
        interval: list
            [a,b] where a and b are the lower and upper bound of the interval to track.
        '''
        if not self.polishing:
            self.interval_results[name].append(interval)
        self.current_area += np.prod(interval[1] - interval[0])

    def print_progress(self):
        ''' Prints the progress of subdivision solve. Only prints every 100th time this function is
            called to save time.
        '''
        self.tick += 1
        if self.tick >= 100:
            self.tick = 0
            if not self.polishing:
                print("\rPercent Finished: {}%       ".format(round(100*self.current_area/self.total_area,2)), end='')
            else:
                print_string =  '\rPolishing Round: {}'.format(self.polish_num)
                print_string += ' Interval: {}/{}:'.format(self.polish_interval_num, len(self.polish_intervals))
                print_string += " Percent Finished: {}%{}".format(round(100*self.current_area/self.total_area,2), ' '*20)
                print(print_string, end='')

    def print_results(self):
        ''' Prints the results of subdivision solve, how many intervals there were and what percent were
            solve by each check/method.
        '''
        results_numbers = np.array([len(self.interval_results[name]) for name in self.interval_results])
        total_intervals = sum(results_numbers)
        self.total_intervals = total_intervals
        checkers = [name for name in self.interval_results]
        print("Total intervals checked was {}".format(total_intervals))
        print("Methods used were {}".format(checkers))
        print("The percent solved by each was {}".format((100*results_numbers / total_intervals).round(4)))

    def plot_results(self, funcs, zeros, plot_intervals, print_plot=True):
        ''' Prints the results of subdivision solve. Only works if the functions are two dimensional.

        Parameters
        ----------
        funcs : list
            A list of the functions the were solved
        zeros: numpy array
            Each row is a zero of the funcitons
        plot_intervals: bool
            If true, shows on the plot which areas were solved by which check/method.
        '''
        #colors: use alpha = .5, dark green, black, orange roots. Change colors of check info plots
        #3D plot with small alpha, matplotlib interactive, animation
        #make logo
        #make easier to input lower/upper bounds as a list
        plt.figure(dpi=600)
        fig,ax = plt.subplots(1)
        fig.set_size_inches(6.5, 3)
        plt.xlim(self.a[0],self.b[0])
        plt.xlabel('$x$')
        plt.ylim(self.a[1],self.b[1])
        plt.ylabel('$y$')
        plt.title('Zero-Loci and Roots')

        dim = 2

        #print the contours
        contour_colors = ['#003cff','#50c878'] #royal blue and emerald green
        x = np.linspace(self.a[0],self.b[0],1000)
        y = np.linspace(self.a[1],self.b[1],1000)
        X,Y = np.meshgrid(x,y)
        for i in range(dim):
            if isinstance(funcs[i], Polynomial):
                Z = np.zeros_like(X)
                for spot,num in np.ndenumerate(X):
                    Z[spot] = funcs[i]([X[spot],Y[spot]])
                plt.contour(X,Y,Z,levels=[0],colors=contour_colors[i])
            else:
                plt.contour(X,Y,funcs[i](X,Y),levels=[0],colors=contour_colors[i])

        colors = ['w','#c3c3c3', 'C8', '#708090', '#897A57', '#D6C7A4','#73e600','#ccff99']
        #colors = ['w','#d3d3d3', '#708090', '#c5af7d', '#897A57', '#D6C7A4','#73e600','#ccff99']

        if plot_intervals:
            plt.title('')
            #plt.title('What happened to the intervals')
            #plot results
            i = -1
            for check in self.interval_results:
                i += 1
                results = self.interval_results[check]
                first = True
                for data in results:
                    a0,b0 = data
                    if first:
                        first = False
                        rect = patches.Rectangle((a0[0],a0[1]),b0[0]-a0[0],b0[1]-a0[1],linewidth=.1,\
                                                 edgecolor='red',facecolor=colors[i], label=check)
                    else:
                        rect = patches.Rectangle((a0[0],a0[1]),b0[0]-a0[0],b0[1]-a0[1],linewidth=.1,\
                                                 edgecolor='red',facecolor=colors[i])
                    ax.add_patch(rect)
            plt.legend()

        #Plot the zeros
        if len(zeros) > 0:
            plt.plot(np.real(zeros[:,0]), np.real(zeros[:,1]),'o',color='#ff0000',markeredgecolor='#ff0000',markersize=3,
                 zorder=22)

        if print_plot:
            plt.savefig('intervals.pdf', bbox_inches='tight')
        plt.show()

def constant_term_check(test_coeff, tol):
    """One of interval_checks

    Checks if the constant term is bigger than all the other terms combined, using the fact that
    each Chebyshev monomial is bounded by 1.

    Parameters
    ----------
    test_coeff : numpy array
        The coefficient matrix of the polynomial to check
    tol: float
        The bound of the sup norm error of the chebyshev approximation.

    Returns
    -------
    constant_term_check : bool
        False if the function is guarenteed to never be zero in the unit box, True otherwise
    """
    test_sum = np.sum(np.abs(test_coeff))
    if fabs(test_coeff[tuple([0]*test_coeff.ndim)]) * 2 > test_sum + tol:
        return False
    else:
        return True

def quadratic_check(test_coeff, intervals,tol):
    """One of subinterval_checks

    Finds the min of the absolute value of the quadratic part, and compares to the sum of the
    rest of the terms. quadratic_check_2D and quadratic_check_3D are faster so runs those if it can,
    otherwise it runs the genereic n-dimensional version.

    Parameters
    ----------
    test_coeff_in : numpy array
        The coefficient matrix of the polynomial to check
    intervals : list
        A list of the intervals to check.
    tol: float
        The bound of the sup norm error of the chebyshev approximation.

    Returns
    -------
    mask : list
        A list of the results of each interval. False if the function is guarenteed to never be zero
        in the unit box, True otherwise
    """
    if test_coeff.ndim == 2:
        return quadratic_check_2D(test_coeff, intervals, tol)
    elif test_coeff.ndim == 3:
        return quadratic_check_3D(test_coeff, intervals, tol)
    else:
        return quadratic_check_nd(test_coeff, intervals, tol)

def quadratic_check_2D(test_coeff, intervals, tol):
    """One of subinterval_checks

    Finds the min of the absolute value of the quadratic part, and compares to the sum of the
    rest of the terms. There can't be a root if min(extreme_values) > other_sum	or if
    max(extreme_values) < -other_sum. We can short circuit and finish
    faster as soon as we find one value that is < other_sum and one value that > -other_sum.

    Parameters
    ----------
    test_coeff_in : numpy array
        The coefficient matrix of the polynomial to check
    intervals : list
        A list of the intervals to check.
    tol: float
        The bound of the sup norm error of the chebyshev approximation.

    Returns
    -------
    mask : list
        A list of the results of each interval. False if the function is guarenteed to never be zero
        in the unit box, True otherwise
    """
    mask = [True]*len(intervals)

    if test_coeff.ndim != 2:
        return mask

    #Get the coefficients of the quadratic part
    #Need to account for when certain coefs are zero.
    #Padding is slow, so check the shape instead.
    c = [0]*6
    shape = test_coeff.shape
    c[0] = test_coeff[0,0]
    if shape[0] > 1:
        c[1] = test_coeff[1,0]
    if shape[1] > 1:
        c[2] = test_coeff[0,1]
    if shape[0] > 2:
        c[3] = test_coeff[2,0]
    if shape[0] > 1 and shape[1] > 1:
        c[4] = test_coeff[1,1]
    if shape[1] > 2:
        c[5] = test_coeff[0,2]

    # The sum of the absolute values of the other coefs
    # Note: Overhead for instantiating a NumPy array is too costly for
    #  small arrays, so the second sum here is faster than using numpy
    other_sum = np.sum(np.abs(test_coeff)) - sum([fabs(coeff) for coeff in c]) + tol


    # Function for evaluating c0 + c1 T_1(x) + c2 T_1(y) +c3 T_2(x) + c4 T_1(x)T_1(y) + c5 T_2(y)
    # Use the Horner form because it is much faster, also do any repeated computatons in advance
    k0 = c[0]-c[3]-c[5]
    k3 = 2*c[3]
    k5 = 2*c[5]
    def eval_func(x,y):
        return k0 + (c[1] + k3 * x + c[4] * y) * x  + (c[2] + k5 * y) * y

    #The interior min
    #Comes from solving dx, dy = 0
    #Dx: 4c3x +  c4y = -c1    Matrix inverse is  [4c5  -c4]
    #Dy:  c4x + 4c5y = -c2                       [-c4  4c3]
    # This computation is the same for all subintevals, so do it first
    det = 16 * c[3] * c[5] - c[4]**2
    if det != 0:
        int_x = (c[2] * c[4] - 4 * c[1] * c[5]) / det
        int_y = (c[1] * c[4] - 4 * c[2] * c[3]) / det
    else:                      # det is zero,
        int_x = np.inf
        int_y = np.inf


    for i, interval in enumerate(intervals):
        min_satisfied, max_satisfied = False,False
        #Check all the corners
        eval = eval_func(interval[0][0], interval[0][1])
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue

        eval = eval_func(interval[1][0], interval[0][1])
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue

        eval = eval_func(interval[0][0], interval[1][1])
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue

        eval = eval_func(interval[1][0], interval[1][1])
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue

        #Check the x constant boundaries
        #The partial with respect to y is zero
        #Dy:  c4x + 4c5y = -c2 =>   y = (-c2-c4x)/(4c5)
        if c[5] != 0:
            cc5 = 4 * c[5]
            x = interval[0][0]
            y = -(c[2] + c[4]*x)/cc5
            if interval[0][1] < y < interval[1][1]:
                eval = eval_func(x,y)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            x = interval[1][0]
            y = -(c[2] + c[4]*x)/cc5
            if interval[0][1] < y < interval[1][1]:
                eval = eval_func(x,y)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Check the y constant boundaries
        #The partial with respect to x is zero
        #Dx: 4c3x +  c4y = -c1  =>  x = (-c1-c4y)/(4c3)
        if c[3] != 0:
            cc3 = 4*c[3]
            y = interval[0][1]
            x = -(c[1] + c[4]*y)/cc3
            if interval[0][0] < x < interval[1][0]:
                eval = eval_func(x,y)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

            y = interval[1][1]
            x = -(c[1] + c[4]*y)/cc3
            if interval[0][0] < x < interval[1][0]:
                eval = eval_func(x,y)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Check the interior value
        if interval[0][0] < int_x < interval[1][0] and interval[0][1] < int_y < interval[1][1]:
            eval = eval_func(int_x,int_y)
            min_satisfied = min_satisfied or eval < other_sum
            max_satisfied = max_satisfied or eval > -other_sum
            if min_satisfied and max_satisfied:
                continue

        # No root possible
        mask[i] = False

    return mask

def quadratic_check_3D(test_coeff, intervals, tol):
    """One of subinterval_checks

    Finds the min of the absolute value of the quadratic part, and compares to the sum of the
    rest of the terms.  There can't be a root if min(extreme_values) > other_sum	or if
    max(extreme_values) < -other_sum. We can short circuit and finish
    faster as soon as we find one value that is < other_sum and one value that > -other_sum.

    Parameters
    ----------
    test_coeff_in : numpy array
        The coefficient matrix of the polynomial to check
    intervals : list
        A list of the intervals to check.
    tol: float
        The bound of the sup norm error of the chebyshev approximation.

    Returns
    -------
    mask : list
        A list of the results of each interval. False if the function is guarenteed to never be zero
        in the unit box, True otherwise
    """
    mask = [True]*len(intervals)

    if test_coeff.ndim != 3:
        return mask

    #Padding is slow, so check the shape instead.
    c = [0]*10
    shape = test_coeff.shape
    c[0] = test_coeff[0,0,0]
    if shape[0] > 1:
        c[1] = test_coeff[1,0,0]
    if shape[1] > 1:
        c[2] = test_coeff[0,1,0]
    if shape[2] > 1:
        c[3] = test_coeff[0,0,1]
    if shape[0] > 1 and shape[1] > 1:
        c[4] = test_coeff[1,1,0]
    if shape[0] > 1 and shape[2] > 1:
        c[5] = test_coeff[1,0,1]
    if shape[1] > 1 and shape[2] > 1:
        c[6] = test_coeff[0,1,1]
    if shape[0] > 2:
        c[7] = test_coeff[2,0,0]
    if shape[1] > 2:
        c[8] = test_coeff[0,2,0]
    if shape[2] > 2:
        c[9] = test_coeff[0,0,2]

    #The sum of the absolute values of everything else
    other_sum = np.sum(np.abs(test_coeff)) - sum([fabs(coeff) for coeff in c]) + tol

    #function for evaluating c0 + c1x + c2y +c3z + c4xy + c5xz + c6yz + c7T_2(x) + c8T_2(y) + c9T_2(z)
    # Use the Horner form because it is much faster, also do any repeated computatons in advance
    k0 = c[0]-c[7]-c[8]-c[9]
    k7 = 2*c[7]
    k8 = 2*c[8]
    k9 = 2*c[9]
    def eval_func(x,y,z):
        return k0 + (c[1] + k7 * x + c[4] * y + c[5] * z) * x + \
                    (c[2] + k8 * y + c[6] * z) * y + \
                    (c[3] + k9 * z) * z

    #The interior min
    #Comes from solving dx, dy, dz = 0
    #Dx: 4c7x +  c4y +  c5z = -c1    Matrix inverse is  [(16c8c9-c6^2) -(4c4c9-c5c6)  (c4c6-4c5c8)]
    #Dy:  c4x + 4c8y +  c6z = -c2                       [-(4c4c9-c5c6) (16c7c9-c5^2) -(4c6c7-c4c5)]
    #Dz:  c5x +  c6y + 4c9z = -c3                       [(c4c6-4c5c8)  -(4c6c7-c4c5) (16c7c8-c4^2)]
    #These computations are the same for all subintevals, so do them first
    kk7 = 2*k7 #4c7
    kk8 = 2*k8 #4c8
    kk9 = 2*k9 #4c9
    fix_x_det = kk8*kk9-c[6]**2
    fix_y_det = kk7*kk9-c[5]**2
    fix_z_det = kk7*kk8-c[4]**2
    minor_1_2 = kk9*c[4]-c[5]*c[6]
    minor_1_3 = c[4]*c[6]-kk8*c[5]
    minor_2_3 = kk7*c[6]-c[4]*c[5]
    det = 4*c[7]*fix_x_det - c[4]*minor_1_2 + c[5]*minor_1_3
    if det != 0:
        int_x = (c[1]*-fix_x_det + c[2]*minor_1_2  + c[3]*-minor_1_3)/det
        int_y = (c[1]*minor_1_2  + c[2]*-fix_y_det + c[3]*minor_2_3)/det
        int_z = (c[1]*-minor_1_3  + c[2]*minor_2_3  + c[3]*-fix_z_det)/det
    else:
        int_x = np.inf
        int_y = np.inf
        int_z = np.inf

    for i, interval in enumerate(intervals):
        #easier names for each value...
        x0 = interval[0][0]
        x1 = interval[1][0]
        y0 = interval[0][1]
        y1 = interval[1][1]
        z0 = interval[0][2]
        z1 = interval[1][2]

        min_satisfied, max_satisfied = False,False
        #Check all the corners
        eval = eval_func(x0, y0, z0)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x1, y0, z0)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x0, y1, z0)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x0, y0, z1)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x1, y1, z0)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x1, y0, z1)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x0, y1, z1)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        eval = eval_func(x1, y1, z1)
        min_satisfied = min_satisfied or eval < other_sum
        max_satisfied = max_satisfied or eval > -other_sum
        if min_satisfied and max_satisfied:
            continue
        #Adds the x and y constant boundaries
        #The partial with respect to z is zero
        #Dz:  c5x +  c6y + 4c9z = -c3   => z=(-c3-c5x-c6y)/(4c9)
        if c[9] != 0:
            c5x0_c3 = c[5]*x0 + c[3]
            c6y0 = c[6]*y0
            z = -(c5x0_c3+c6y0)/kk9
            if z0 < z < z1:
                eval = eval_func(x0,y0,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c6y1 = c[6]*y1
            z = -(c5x0_c3+c6y1)/kk9
            if z0 < z < z1:
                eval = eval_func(x0,y1,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c5x1_c3 = c[5]*x1 + c[3]
            z = -(c5x1_c3+c6y0)/kk9
            if z0 < z < z1:
                eval = eval_func(x1,y0,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            z = -(c5x1_c3+c6y1)/kk9
            if z0 < z < z1:
                eval = eval_func(x1,y1,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Adds the x and z constant boundaries
        #The partial with respect to y is zero
        #Dy:  c4x + 4c8y + c6z = -c2   => y=(-c2-c4x-c6z)/(4c8)
        if c[8] != 0:
            c6z0 = c[6]*z0
            c2_c4x0 = c[2]+c[4]*x0
            y = -(c2_c4x0+c6z0)/kk8
            if y0 < y < y1:
                eval = eval_func(x0,y,z0)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c6z1 = c[6]*z1
            y = -(c2_c4x0+c6z1)/kk8
            if y0 < y < y1:
                eval = eval_func(x0,y,z1)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c2_c4x1 = c[2]+c[4]*x1
            y = -(c2_c4x1+c6z0)/kk8
            if y0 < y < y1:
                eval = eval_func(x1,y,z0)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            y = -(c2_c4x1+c6z1)/kk8
            if y0 < y < y1:
                eval = eval_func(x1,y,z1)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Adds the y and z constant boundaries
        #The partial with respect to x is zero
        #Dx: 4c7x +  c4y +  c5z = -c1   => x=(-c1-c4y-c5z)/(4c7)
        if c[7] != 0:
            c1_c4y0 = c[1]+c[4]*y0
            c5z0 = c[5]*z0
            x = -(c1_c4y0+c5z0)/kk7
            if x0 < x < x1:
                eval = eval_func(x,y0,z0)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c5z1 = c[5]*z1
            x = -(c1_c4y0+c5z1)/kk7
            if x0 < x < x1:
                eval = eval_func(x,y0,z1)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c1_c4y1 = c[1]+c[4]*y1
            x = -(c1_c4y1+c5z0)/kk7
            if x0 < x < x1:
                eval = eval_func(x,y1,z0)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            x = -(c1_c4y1+c5z1)/kk7
            if x0 < x < x1:
                eval = eval_func(x,y1,z1)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Add the x constant boundaries
        #The partials with respect to y and z are zero
        #Dy:  4c8y +  c6z = -c2 - c4x    Matrix inverse is [4c9  -c6]
        #Dz:   c6y + 4c9z = -c3 - c5x                      [-c6  4c8]
        if fix_x_det != 0:
            c2_c4x0 = c[2]+c[4]*x0
            c3_c5x0 = c[3]+c[5]*x0
            y = (-kk9*c2_c4x0 +   c[6]*c3_c5x0)/fix_x_det
            z = (c[6]*c2_c4x0 -    kk8*c3_c5x0)/fix_x_det
            if y0 < y < y1 and z0 < z < z1:
                eval = eval_func(x0,y,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c2_c4x1 = c[2]+c[4]*x1
            c3_c5x1 = c[3]+c[5]*x1
            y = (-kk9*c2_c4x1 +   c[6]*c3_c5x1)/fix_x_det
            z = (c[6]*c2_c4x1 -    kk8*c3_c5x1)/fix_x_det
            if y0 < y < y1 and z0 < z < z1:
                eval = eval_func(x1,y,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Add the y constant boundaries
        #The partials with respect to x and z are zero
        #Dx: 4c7x +  c5z = -c1 - c40    Matrix inverse is [4c9  -c5]
        #Dz:  c5x + 4c9z = -c3 - c6y                      [-c5  4c7]
        if fix_y_det != 0:
            c1_c4y0 = c[1]+c[4]*y0
            c3_c6y0 = c[3]+c[6]*y0
            x = (-kk9*c1_c4y0 +   c[5]*c3_c6y0)/fix_y_det
            z = (c[5]*c1_c4y0 -    kk7*c3_c6y0)/fix_y_det
            if x0 < x < x1 and z0 < z < z1:
                eval = eval_func(x,y0,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c1_c4y1 = c[1]+c[4]*y1
            c3_c6y1 = c[3]+c[6]*y1
            x = (-kk9*c1_c4y1 +   c[5]*c3_c6y1)/fix_y_det
            z = (c[5]*c1_c4y1 -    kk7*c3_c6y1)/fix_y_det
            if x0 < x < x1 and z0 < z < z1:
                eval = eval_func(x,y1,z)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Add the z constant boundaries
        #The partials with respect to x and y are zero
        #Dx: 4c7x +  c4y  = -c1 - c5z    Matrix inverse is [4c8  -c4]
        #Dy:  c4x + 4c8y  = -c2 - c6z                      [-c4  4c7]
        if fix_z_det != 0:
            c1_c5z0 = c[1]+c[5]*z0
            c2_c6z0 = c[2]+c[6]*z0
            x = (-kk8*c1_c5z0 +   c[4]*c2_c6z0)/fix_z_det
            y = (c[4]*c1_c5z0 -    kk7*c2_c6z0)/fix_z_det
            if x0 < x < x1 and y0 < y < y1:
                eval = eval_func(x,y,z0)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue
            c1_c5z1 = c[1]+c[5]*z1
            c2_c6z1 = c[2]+c[6]*z1
            x = (-kk8*c1_c5z1 +   c[4]*c2_c6z1)/fix_z_det
            y = (c[4]*c1_c5z1 -    kk7*c2_c6z1)/fix_z_det
            if x0 < x < x1 and y0 < y < y1:
                eval = eval_func(x,y,z1)
                min_satisfied = min_satisfied or eval < other_sum
                max_satisfied = max_satisfied or eval > -other_sum
                if min_satisfied and max_satisfied:
                    continue

        #Add the interior value
        if x0 < int_x < x1 and y0 < int_y < y1 and\
                z0 < int_z < z1:
            eval = eval_func(int_x,int_y,int_z)
            min_satisfied = min_satisfied or eval < other_sum
            max_satisfied = max_satisfied or eval > -other_sum
            if min_satisfied and max_satisfied:
                continue

        # No root possible
        mask[i] = False

    return mask

@memoize
def get_fixed_vars(dim):
    """Used in quadratic_check_nd to iterate through the boundaries of the domain.

    Parameters
    ----------
    dim : int
        The dimension of the domain/system.

    Returns
    -------
    list of tuples
        A list of tuples indicating which variables to fix in each iteration,
        starting at fixing dim-1 of them and ending with fixing 1 of them. This
        intentionally excludes combinations that correspond to the corners of the
        domain and the interior extremum.
    """
    return list(itertools.chain.from_iterable(itertools.combinations(range(dim), r)\
                                             for r in range(dim-1,0,-1)))

def quadratic_check_nd(test_coeff, intervals, tol):
    """One of subinterval_checks

    Finds the min of the absolute value of the quadratic part, and compares to the sum of the
    rest of the terms. There can't be a root if min(extreme_values) > other_sum	or if
    max(extreme_values) < -other_sum. We can short circuit and finish
    faster as soon as we find one value that is < other_sum and one value that > -other_sum.

    Parameters
    ----------
    test_coeff_in : numpy array
        The coefficient matrix of the polynomial to check
    intervals : list
        A list of the intervals to check.
    tol: float
        The bound of the sup norm error of the chebyshev approximation.

    Returns
    -------
    mask : list
        A list of the results of each interval. False if the function is guarenteed to never be zero
        in the unit box, True otherwise
    """
    mask = [True]*len(intervals)
    #get the dimension and make sure the coeff tensor has all the right
    # quadratic coeff spots, set to zero if necessary
    dim = test_coeff.ndim
    padding = [(0,max(0,3-i)) for i in test_coeff.shape]
    test_coeff = np.pad(test_coeff.copy(), padding, mode='constant')

    #Possible extrema of qudaratic part are where D_xk = 0 for some subset of the variables xk
    # with the other variables are fixed to a boundary value
    #Dxk = c[0,...,0,1,0,...0] (k-spot is 1) + 4c[0,...,0,2,0,...0] xk (k-spot is 2)
    #       + \Sum_{j\neq k} xj c[0,...,0,1,0,...,0,1,0,...0] (k and j spot are 1)
    #This gives a symmetric system of equations AX+B = 0
    #We will fix different columns of X each time, resulting in slightly different
    #systems, but storing A and B now will be helpful later

    #pull out coefficients we care about
    quad_coeff = np.zeros([3]*dim)
    #A and B are arrays for slicing
    A = np.zeros([dim,dim])
    B = np.zeros(dim)
    pure_quad_coeff = [0]*dim
    for spot in itertools.product(range(3),repeat=dim):
        spot_deg = sum(spot)
        if spot_deg == 1:
            #coeff of linear terms
            i = [idx for idx in range(dim) if spot[idx]!= 0][0]
            B[i] = test_coeff[spot].copy()
            quad_coeff[spot] = test_coeff[spot]
            test_coeff[spot] = 0
        elif spot_deg == 0:
            #constant term
            const = test_coeff[spot].copy()
            quad_coeff[spot] = const
            test_coeff[spot] = 0
        elif spot_deg < 3:
            where_nonzero = [idx for idx in range(dim) if spot[idx]!= 0]
            if len(where_nonzero) == 2:
                #coeff of cross terms
                i,j = where_nonzero
                #with symmetric matrices, we only need to store the lower part
                A[j,i] = test_coeff[spot].copy()
                A[i,j] = A[j,i]
                #todo: see if we can store this in only one half of A
               
            else:
                #coeff of pure quadratic terms
                i = where_nonzero[0]
                pure_quad_coeff[i] = test_coeff[spot].copy()
            quad_coeff[spot] = test_coeff[spot]
            test_coeff[spot] = 0
    pure_quad_coeff_doubled = [p*2 for p in pure_quad_coeff]
    A[np.diag_indices(dim)] = [p*2 for p in pure_quad_coeff_doubled]

    #create a poly object for evals
    k0 = const - sum(pure_quad_coeff)
    def eval_func(point):
        "fast evaluation of quadratic chebyshev polynomials using horner's algorithm"
        _sum = k0
        for i,coord in enumerate(point):
            _sum += (B[i] + pure_quad_coeff_doubled[i]*coord + \
                     sum([A[i,j]*point[j] for j in range(i+1,dim)])) * coord
        return _sum

    #The sum of the absolute values of everything else
    other_sum = np.sum(np.abs(test_coeff)) + tol

    #iterator for sides
    fixed_vars = get_fixed_vars(dim)

    for k, interval in enumerate(intervals):
        Done = False
        min_satisfied, max_satisfied = False,False
        #fix all variables--> corners
        for corner in itertools.product([0,1],repeat=dim):
            #j picks if upper/lower bound. i is which var
            eval = eval_func([interval[j][i] for i,j in enumerate(corner)])
            min_satisfied = min_satisfied or eval < other_sum
            max_satisfied = max_satisfied or eval > -other_sum
            if min_satisfied and max_satisfied:
                Done = True
                break
        #need to check sides/interior
        if not Done:
            X = np.zeros(dim)
            for fixed in fixed_vars:
                #fixed some variables --> "sides"
                #we only care about the equations from the unfixed variables
                fixed = np.array(fixed)
                unfixed = np.delete(np.arange(dim), fixed)
                A_ = A[unfixed][:,unfixed]
                #if diagonal entries change sign, can't be definite
                diag = np.diag(A_)
                for i,c in enumerate(diag[:-1]):
                    #sign change?
                    if c*diag[i+1]<0:
                        break
                #if no sign change, can find extrema
                else:
                    #not full rank --> no soln
                    if np.linalg.matrix_rank(A_,hermitian=True) == A_.shape[0]:
                        fixed_A = A[unfixed][:,fixed]
                        B_ = B[unfixed]
                        for side in itertools.product([0,1],repeat=len(fixed)):
                            X0 = np.array([interval[j][i] for i,j in enumerate(side)])
                            X_ = la.solve(A_, -B_-fixed_A@X0, assume_a='sym')
                            #make sure it's in the domain
                            for i,var in enumerate(unfixed):
                                if interval[0][var] <= X_[i] <= interval[1][var]:
                                    continue
                                else:
                                    break
                            else:
                                X[fixed] = X0
                                X[unfixed] = X_
                                eval = eval_func(X)
                                min_satisfied = min_satisfied or eval < other_sum
                                max_satisfied = max_satisfied or eval > -other_sum
                                if min_satisfied and max_satisfied:
                                    Done = True
                                    break
                if Done:
                    break
            else:
                #fix no vars--> interior
                #if diagonal entries change sign, can't be definite
                for i,c in enumerate(pure_quad_coeff[:-1]):
                    #sign change?
                    if c*pure_quad_coeff[i+1]<0:
                        break
                #if no sign change, can find extrema
                else:
                    #not full rank --> no soln
                    if np.linalg.matrix_rank(A,hermitian=True) == A.shape[0]:
                        X = la.solve(A, -B, assume_a='sym')
                        #make sure it's in the domain
                        for i in range(dim):
                            if interval[0][i] <= X[i] <= interval[1][i]:
                                continue
                            else:
                                break
                        else:
                            eval = eval_func(X)
                            min_satisfied = min_satisfied or eval < other_sum
                            max_satisfied = max_satisfied or eval > -other_sum
                            if min_satisfied and max_satisfied:
                                Done = True
        #no root
        if not Done:
            mask[k] = False

    return mask

def slices_max_min_check(test_coeff, intervals, tol):
    dim = test_coeff.ndim
    #at first just implement WRT x
    mask = [True]*len(intervals)
    #pull out the slices
    # min_slice =

    for i, interval in enumerate(intervals):
        Done = False
        #check interval

        #no root
        if not Done:
            mask[i] = False

    return mask
