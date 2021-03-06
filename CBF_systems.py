#!/usr/bin/env python
'''
control systems with general CBF implementations
'''
import numpy as np
from math import ceil, log
from systems import *
from quadprog import solve_qp


class CBFSystem(ControlSystem):
    '''
    System with Control Barrier Formulation
    '''
    def __init__(self, x, G=None):
        ControlSystem.__init__(self, x)

        if not G:
            self.G = np.identity(np.shape(self.g())[1])

    # feedback controller using CBF
    def u(self):
        ud = self.nominal()  # u nominal
        u_opt = self.qp_u(ud)  # safe controller
        return u_opt

    # nominal controller
    def nominal(self):
        raise NotImplementedError

    # actuation constraints
    def input_cons(self):
        raise NotImplementedError
        # return (Ca, ba)

    # control barrier: returns safety constraints
    def CBF(self):
        raise NotImplementedError

    # QP solver
    def qp_u(self, ud):
        Cc, bc = self.CBF()
        Ca, ba = self.input_cons()
        # parameters for solve_qp

        A = np.hstack((Cc, Ca))
        b = np.concatenate((bc, ba))

        try:
            u_opt = solve_qp(self.G, ud, A, b)[0]
        except:
            u_opt = np.array([0, 0])

        return u_opt


class FeasibleCBF(CBFSystem):
    '''
    Feasible Control Barrier Formulation
    '''
    def __init__(self, x, h, gamma, a):
        CBFSystem.__init__(self, x)
        self.h = h  # barrier function
        self.gamma = gamma  # evasive maneuver
        self.a = a  # class K function
        self.epsilon = 0.0  # higher epsilon promotes conservatism

    # numerical calculation of gradient of h
    def gradh(self):
        x_cop = np.copy(self.x)
        n = len(self.x)
        grad = np.zeros((n,))
        step = .0001

        for i in range(n):
            dh = []
            for dx in [-step, step]:
                dx_state = self.x[i] + dx
                x_cop[i] = dx_state
                dh.append(self.h(x_cop))
            # median approximation
            grad[i] = np.diff(dh)/(2*step)
        return grad

    # control barrier function
    def CBF(self):
        h_dot = self.gradh()

        Lfh = h_dot @ self.f()
        Lgh = h_dot @ self.g()
        alpha = self.a(self.h(self.x))
        print('ffff',self.h(self.x))
        C = np.reshape(np.array(Lgh), (-1, 1))
        b = np.array([-(alpha + Lfh)])
        return C, b + self.epsilon


class CoupleCBF(FeasibleCBF, NetworkSystem):
    '''
    Feasible Control Barrier Formulations for Coupled Systems
    '''
    def __init__(self, x, h=None, ch=None, sys_list=[], gamma=None, a=None, ach=None):
        FeasibleCBF.__init__(self, x, h, gamma, a)
        NetworkSystem.__init__(self, x, sys_list)
        self.ch = ch  # barrier between the coupled system
        self.ach = ach  # class K function for coupled barrier

    # feedback controller using coupled CBF
    def u(self):
        nom = self.nominal()
        print('good')

        if self.sys_list:
            sysnom = np.concatenate([sys.nominal() for sys in self.sys_list])
            ud = np.concatenate((nom, sysnom))
        else:
            ud = nom
        u_opt = self.qp_u(ud)
        return u_opt[0:np.shape(self.g())[1]]

    # numerical calculation of gradient of barrier between 2 systems
    def gradch(self, j):
        xi = np.copy(self.x)
        xj = np.copy(self.sys_list[j].x)
        n = len(xi)
        grad = np.zeros((2*n,))
        step = .001

        for i in range(2*n):
            dh = []
            for dx in [-step, step]:
                if i < n:
                    dxstate = self.x[i] + dx
                    xi[i] = dxstate
                else:
                    dxstate = self.sys_list[j].x[i-n] + dx
                    xj[i-n] = dxstate
                dh.append(self.ch(xi, xj))
            # median approximation
            grad[i] = np.diff(dh)/(2*step)
        return grad

    # Control barrier function for coupled system
    def chCBF(self):
        length = len(self.sys_list)
        if length == 0 or not self.ch:
            return None

        C = np.zeros((len(self.g()[1])*(length + 1), length))
        b = np.zeros((length,))

        for j in range(length):
            sysj = self.sys_list[j]

            gradient = self.gradch(j)
            h_dot = gradient[0:len(self.x)]
            h_dot_j = gradient[len(self.x):]

            Lfh = h_dot @ self.f()
            Lgh = h_dot @ self.g()

            Lfhj = h_dot_j @ sysj.f()
            Lghj = h_dot_j @ sysj.g()

            alpha = self.ach((self.ch(self.x, sysj.x)))

            l = len(self.g()[1])

            C[0:l, j] = Lgh
            C[l*(j+1):l*(j+2), j] = Lghj

            b[j] = -(alpha + Lfh + Lfhj)

        return C, b + self.epsilon

    # control barrier function for barrier
    def hCBF(self):
        h_dot = self.gradh()

        Lfh = h_dot @ self.f()
        Lgh = h_dot @ self.g()
        alpha = self.a(self.h(self.x))

        C = np.array(Lgh)
        b = np.array([-(alpha + Lfh)])
        return C, b + self.epsilon

    def CBF(self):
        l = np.shape(self.g())[1]
        n = l*(len(self.sys_list)+1)
        if self.h:
            Ch, bh = self.hCBF()
            temp = np.zeros((n,))
            temp[0:l] = Ch
            Ch = np.reshape(temp, (n, 1))
        else:
            Ch, bh = (np.zeros((n, 1)), np.array([0]))
        if self.ch and self.sys_list:
            Cch, bch = self.chCBF()
        else:
            Cch, bch = (np.zeros((n, 1)), np.array([0]))

        C = np.hstack((Ch, Cch))
        b = np.concatenate((bh, bch))
        return C, b