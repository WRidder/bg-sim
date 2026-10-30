import numpy as np

#Transformation to get the right ouput compared to Coppelia/Drake
def transform_joint_data(q, qd, qdd):
    """
    Applies a transformation to joint position, velocity, and acceleration arrays.

    Parameters:
    - q: numpy array of joint positions, shape (n, m)
    - qd: numpy array of joint velocities
    - qdd: numpy array of joint accelerations

    Returns:
    - Transformed q, qd, qdd
    """

    offset = -np.pi / 2
    q = -np.array(q)

    if q.ndim == 2:
        q[:, 0] += offset
    elif q.ndim == 1:
        q[0] += offset

    qd = -np.array(qd)
    qdd = -np.array(qdd)
    return q, qd, qdd



class PlanarRobot:
    def __init__(self, links, payload, gravity):
        """
        links: list of externally created Link objects
        """
        if not links:
            raise ValueError("Robot must have at least one link.")
        
        self.links = links #list
        self.payload = payload #link object RBT 
        self.gravity = np.abs(gravity) #scalar

        #Link Parameters listed
        self.d = [link.d for link in self.links]
        self.a = [link.a for link in self.links]
        self.alpha = [link.alpha for link in self.links]
        self.m = [link.m for link in self.links]
        self.r = [link.r[0] for link in self.links]
        self.ry = [link.r[1] for link in self.links]
        self.I = [link.I[2,2] for link in self.links]
        self.B = [link.B for link in self.links]
        self.G = [link.G for link in self.links]
        self.Jm = [link.Jm for link in self.links]

        #Payload parameters listed
        self.pay_m = self.payload[0]
        self.pay_I = self.payload[1]
        self.pay_r = self.payload[2][0]
        self.pay_ry = self.payload[2][1]

    def get_total_mass(self):
        total_mass = sum(link.m for link in self.links)
        total_mass += self.payload
        return total_mass
        
    def __repr__(self):
        return f"PlanarRobot({len(self.links)} links)"

class OneLinkRobot(PlanarRobot):
    def __init__(self, link1, pay_m, pay_I, pay_r, gravity):
        super().__init__(links=[link1], payload=[pay_m, pay_I, pay_r], gravity=gravity)

    def tau(self, q, qd, qdd):
        
        self.q = q
        self.qd = qd
        self.qdd = qdd

        d = self.d; a = self.a; alpha = self.alpha; m = self.m; r = self.r
        I = self.I; B = self.B; G = self.G; Jm = self.Jm; g = self.gravity
        q = self.q; qd = self.qd; qdd = self.qdd
        
        tau_m = qdd[:]*(G[0]**2*Jm[0] + I[0] + m[0]*(a[0] + r[0])**2)
        tau_c = 0
        tau_g = g*m[0]*(a[0] + r[0])*np.cos(q[:])
        tau_visc = B[0]*G[0]**2*qd[:]
        tau = tau_m + tau_c + tau_g + tau_visc
        
        return tau

class TwoLinkRobot(PlanarRobot):
    def __init__(self, link1, link2, pay_m, pay_I, pay_r, gravity):
        super().__init__(links=[link1, link2], payload=[pay_m, pay_I, pay_r], gravity=gravity)

    def tau(self, q, qd, qdd):
        
        self.q = q
        self.qd = qd
        self.qdd = qdd

        d = self.d; a = self.a; alpha = self.alpha; m = self.m; r = (np.array(self.a) + np.array(self.r)) 
        I = self.I; B = self.B; G = self.G; Jm = self.Jm; g = self.gravity
        q = self.q; qd = self.qd; qdd = self.qdd
      

        tau_m = []; tau_c = []; tau_g = []; tau_visc = []
        for i in range(len(q)):
          
            tau_m_temp =  np.array([[G[0] ** 2 * Jm[0] + I[0] + I[1] + m[0] * r[0] ** 2 + m[1] * (a[0] ** 2 + 2 * a[0] * r[1] * np.cos(q[i,1]) + r[1] ** 2), I[1] + m[1] * r[1] * (a[0] * np.cos(q[i,1]) + r[1])], [I[1] + m[1] * r[1] * (a[0] * np.cos(q[i,1]) + r[1]), G[1] ** 2 * Jm[1] + I[1] + m[1] * r[1] ** 2]]) @ qdd[i, :] 
            tau_c_temp = np.array([[-1.0 * a[0] * m[1] * qd[i,1] * r[1] * np.sin(q[i,1]), -1.0 * a[0] * m[1] * qd[i,0] * r[1] * np.sin(q[i,1]) - 1.0 * a[0] * m[1] * qd[i,1] * r[1] * np.sin(q[i,1])], [1.0 * a[0] * m[1] * qd[i,0] * r[1] * np.sin(q[i,1]), 0]]) @ qd[i, :]
            tau_g_temp = np.array([g * m[0] * r[0] * np.cos(q[i,0]) + g * m[1] * (a[0] * np.cos(q[i,0]) + r[1] * np.cos(q[i,0] + q[i,1])), g * m[1] * r[1] * np.cos(q[i,0] + q[i,1])]) #remove []!!
            tau_visc_temp = np.array([[B[0] * G[0] ** 2, 0], [0, B[1] * G[1] ** 2]]) @ qd[i, :]
            
            tau_m.append(tau_m_temp)
            tau_c.append(tau_c_temp)
            tau_g.append(tau_g_temp)
            tau_visc.append(tau_visc_temp)
            
            tau = np.array(tau_m)+np.array(tau_c)+np.array(tau_g)+np.array(tau_visc)

        return tau


class ThreeLinkRobot(PlanarRobot):
    def __init__(self, link1, link2, link3, pay_m, pay_I, pay_r, gravity):
        super().__init__(links=[link1, link2, link3], payload=[pay_m, pay_I, pay_r], gravity=gravity)

    def tau(self, q, qd, qdd):
        
        self.q = q
        self.qd = qd
        self.qdd = qdd
    
        d = self.d; a = self.a; alpha = self.alpha; m = self.m; r = (np.array(self.a) + np.array(self.r)); ry = self.ry 
        I = self.I; B = self.B; G = self.G; Jm = self.Jm; g = self.gravity
        q = self.q; qd = self.qd; qdd = self.qdd

        pay_m = self.pay_m; pay_I = self.pay_I; pay_r = self.pay_r; pay_ry = self.pay_ry
      

        tau_m = []; tau_c = []; tau_g = []; tau_visc = []
        for i in range(len(q)):
            
            tau_m_temp = np.array([[G[0] ** 2 * Jm[0] + I[0] + I[1] + I[2] + pay_I + m[0] * (r[0] ** 2 + ry[0] ** 2) + m[1] * (a[0] ** 2 + 2 * a[0] * r[1] * np.cos(q[i,1]) - 2 * a[0] * ry[1] * np.sin(q[i,1]) + r[1] ** 2 + ry[1] ** 2) + m[2] * (a[0] ** 2 + 2 * a[0] * a[1] * np.cos(q[i,1]) + 2 * a[0] * r[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * r[2] * np.cos(q[i,2]) - 2 * a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[0] ** 2 + 2 * a[0] * a[1] * np.cos(q[i,1]) + 2 * a[0] * a[2] * np.cos(q[i,1] + q[i,2]) + 2 * a[0] * pay_r * np.cos(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * a[2] * np.cos(q[i,2]) + 2 * a[1] * pay_r * np.cos(q[i,2]) - 2 * a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), I[1] + I[2] + pay_I + m[1] * (a[0] * r[1] * np.cos(q[i,1]) - a[0] * ry[1] * np.sin(q[i,1]) + r[1] ** 2 + ry[1] ** 2) + m[2] * (a[0] * a[1] * np.cos(q[i,1]) + a[0] * r[2] * np.cos(q[i,1] + q[i,2]) - a[0] * ry[2] * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * r[2] * np.cos(q[i,2]) - 2 * a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[0] * a[1] * np.cos(q[i,1]) + a[0] * a[2] * np.cos(q[i,1] + q[i,2]) + a[0] * pay_r * np.cos(q[i,1] + q[i,2]) - a[0] * pay_ry * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * a[2] * np.cos(q[i,2]) + 2 * a[1] * pay_r * np.cos(q[i,2]) - 2 * a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), I[2] + pay_I + m[2] * (a[0] * r[2] * np.cos(q[i,1] + q[i,2]) - a[0] * ry[2] * np.sin(q[i,1] + q[i,2]) + a[1] * r[2] * np.cos(q[i,2]) - a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[0] * a[2] * np.cos(q[i,1] + q[i,2]) + a[0] * pay_r * np.cos(q[i,1] + q[i,2]) - a[0] * pay_ry * np.sin(q[i,1] + q[i,2]) + a[1] * a[2] * np.cos(q[i,2]) + a[1] * pay_r * np.cos(q[i,2]) - a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2)], [I[1] + I[2] + pay_I + m[1] * (a[0] * r[1] * np.cos(q[i,1]) - a[0] * ry[1] * np.sin(q[i,1]) + r[1] ** 2 + ry[1] ** 2) + m[2] * (a[0] * a[1] * np.cos(q[i,1]) + a[0] * r[2] * np.cos(q[i,1] + q[i,2]) - a[0] * ry[2] * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * r[2] * np.cos(q[i,2]) - 2 * a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[0] * a[1] * np.cos(q[i,1]) + a[0] * a[2] * np.cos(q[i,1] + q[i,2]) + a[0] * pay_r * np.cos(q[i,1] + q[i,2]) - a[0] * pay_ry * np.sin(q[i,1] + q[i,2]) + a[1] ** 2 + 2 * a[1] * a[2] * np.cos(q[i,2]) + 2 * a[1] * pay_r * np.cos(q[i,2]) - 2 * a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), G[1] ** 2 * Jm[1] + I[1] + I[2] + pay_I + m[1] * (r[1] ** 2 + ry[1] ** 2) + m[2] * (a[1] ** 2 + 2 * a[1] * r[2] * np.cos(q[i,2]) - 2 * a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[1] ** 2 + 2 * a[1] * a[2] * np.cos(q[i,2]) + 2 * a[1] * pay_r * np.cos(q[i,2]) - 2 * a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), I[2] + pay_I + m[2] * (a[1] * r[2] * np.cos(q[i,2]) - a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[1] * a[2] * np.cos(q[i,2]) + a[1] * pay_r * np.cos(q[i,2]) - a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2)], [I[2] + pay_I + m[2] * (a[0] * r[2] * np.cos(q[i,1] + q[i,2]) - a[0] * ry[2] * np.sin(q[i,1] + q[i,2]) + a[1] * r[2] * np.cos(q[i,2]) - a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[0] * a[2] * np.cos(q[i,1] + q[i,2]) + a[0] * pay_r * np.cos(q[i,1] + q[i,2]) - a[0] * pay_ry * np.sin(q[i,1] + q[i,2]) + a[1] * a[2] * np.cos(q[i,2]) + a[1] * pay_r * np.cos(q[i,2]) - a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), I[2] + pay_I + m[2] * (a[1] * r[2] * np.cos(q[i,2]) - a[1] * ry[2] * np.sin(q[i,2]) + r[2] ** 2 + ry[2] ** 2) + pay_m * (a[1] * a[2] * np.cos(q[i,2]) + a[1] * pay_r * np.cos(q[i,2]) - a[1] * pay_ry * np.sin(q[i,2]) + a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2), G[2] ** 2 * Jm[2] + I[2] + pay_I + m[2] * (r[2] ** 2 + ry[2] ** 2) + pay_m * (a[2] ** 2 + 2 * a[2] * pay_r + pay_r ** 2 + pay_ry ** 2)]])  @ qdd[i, :] 
            tau_c_temp = np.array([[qd[i,1] * (0.5 * m[1] * (-2 * a[0] * r[1] * np.sin(q[i,1]) - 2 * a[0] * ry[1] * np.cos(q[i,1])) + 0.5 * m[2] * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]))) + qd[i,2] * (0.5 * m[2] * (-2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), qd[i,0] * (0.5 * m[1] * (-2 * a[0] * r[1] * np.sin(q[i,1]) - 2 * a[0] * ry[1] * np.cos(q[i,1])) + 0.5 * m[2] * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]))) + qd[i,1] * (1.0 * m[1] * (-a[0] * r[1] * np.sin(q[i,1]) - a[0] * ry[1] * np.cos(q[i,1])) + 1.0 * m[2] * (-a[0] * a[1] * np.sin(q[i,1]) - a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 1.0 * pay_m * (-a[0] * a[1] * np.sin(q[i,1]) - a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]))) + qd[i,2] * (0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), qd[i,0] * (0.5 * m[2] * (-2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,1] * (0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,2] * (1.0 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - a[1] * r[2] * np.sin(q[i,2]) - a[1] * ry[2] * np.cos(q[i,2])) + 1.0 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - a[1] * a[2] * np.sin(q[i,2]) - a[1] * pay_r * np.sin(q[i,2]) - a[1] * pay_ry * np.cos(q[i,2])))], [qd[i,0] * (-0.5 * m[1] * (-2 * a[0] * r[1] * np.sin(q[i,1]) - 2 * a[0] * ry[1] * np.cos(q[i,1])) - 0.5 * m[2] * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) - 0.5 * pay_m * (-2 * a[0] * a[1] * np.sin(q[i,1]) - 2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]))) + qd[i,2] * (-0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) - 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), qd[i,2] * (0.5 * m[2] * (-2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), qd[i,0] * (-0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) + 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) - 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,1] * (0.5 * m[2] * (-2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,2] * (1.0 * m[2] * (-a[1] * r[2] * np.sin(q[i,2]) - a[1] * ry[2] * np.cos(q[i,2])) + 1.0 * pay_m * (-a[1] * a[2] * np.sin(q[i,2]) - a[1] * pay_r * np.sin(q[i,2]) - a[1] * pay_ry * np.cos(q[i,2])))], [qd[i,0] * (-0.5 * m[2] * (-2 * a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) - 0.5 * pay_m * (-2 * a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - 2 * a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,1] * (0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) - 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) - 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), qd[i,0] * (0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2])) - 0.5 * m[2] * (-a[0] * r[2] * np.sin(q[i,1] + q[i,2]) - a[0] * ry[2] * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) + 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2])) - 0.5 * pay_m * (-a[0] * a[2] * np.sin(q[i,1] + q[i,2]) - a[0] * pay_r * np.sin(q[i,1] + q[i,2]) - a[0] * pay_ry * np.cos(q[i,1] + q[i,2]) - 2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))) + qd[i,1] * (-0.5 * m[2] * (-2 * a[1] * r[2] * np.sin(q[i,2]) - 2 * a[1] * ry[2] * np.cos(q[i,2])) - 0.5 * pay_m * (-2 * a[1] * a[2] * np.sin(q[i,2]) - 2 * a[1] * pay_r * np.sin(q[i,2]) - 2 * a[1] * pay_ry * np.cos(q[i,2]))), 0]]) @ qd[i, :]
            tau_g_temp = np.array([g * m[0] * (r[0] * np.cos(q[i,0]) - ry[0] * np.sin(q[i,0])) + g * m[1] * (a[0] * np.cos(q[i,0]) + r[1] * np.cos(q[i,0] + q[i,1]) - ry[1] * np.sin(q[i,0] + q[i,1])) + g * m[2] * (a[0] * np.cos(q[i,0]) + a[1] * np.cos(q[i,0] + q[i,1]) + r[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) - ry[2] * np.sin(q[i,0] + q[i,1] + q[i,2])) + g * pay_m * (a[0] * np.cos(q[i,0]) + a[1] * np.cos(q[i,0] + q[i,1]) + a[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) + pay_r * np.cos(q[i,0] + q[i,1] + q[i,2]) - pay_ry * np.sin(q[i,0] + q[i,1] + q[i,2])), g * m[1] * (r[1] * np.cos(q[i,0] + q[i,1]) - ry[1] * np.sin(q[i,0] + q[i,1])) + g * m[2] * (a[1] * np.cos(q[i,0] + q[i,1]) + r[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) - ry[2] * np.sin(q[i,0] + q[i,1] + q[i,2])) + g * pay_m * (a[1] * np.cos(q[i,0] + q[i,1]) + a[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) + pay_r * np.cos(q[i,0] + q[i,1] + q[i,2]) - pay_ry * np.sin(q[i,0] + q[i,1] + q[i,2])), g * m[2] * (r[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) - ry[2] * np.sin(q[i,0] + q[i,1] + q[i,2])) + g * pay_m * (a[2] * np.cos(q[i,0] + q[i,1] + q[i,2]) + pay_r * np.cos(q[i,0] + q[i,1] + q[i,2]) - pay_ry * np.sin(q[i,0] + q[i,1] + q[i,2]))]) #remove []!!
            tau_visc_temp = np.array([[B[0] * G[0] ** 2, 0, 0], [0, B[1] * G[1] ** 2, 0], [0, 0, B[2] * G[2] ** 2]]) @ qd[i, :]
            
            tau_m.append(tau_m_temp)
            tau_c.append(tau_c_temp)
            tau_g.append(tau_g_temp)
            tau_visc.append(tau_visc_temp)
            
            tau = np.array(tau_m)+np.array(tau_c)+np.array(tau_g)+np.array(tau_visc)
        
        return tau


# Main function
def main():
    import roboticstoolbox as rtb
    import matplotlib.pyplot as plt
    from roboticstoolbox import DHLink
    from roboticstoolbox import DHRobot
    from roboticstoolbox import quintic 
    from roboticstoolbox import jtraj   

    #Link1
    d1=0 #link offset [m]
    a1=0.675 #linkn length [m]
    alpha1=0 #link twist [rad]
    m1=3.815 #link mass [kg]
    r1=np.array([-0.291, 0, 0]) #position of COM with respect to link frame [m]
    I1=np.array([[0, 0, 0],
                [0, 0, 0],
                [0, 0, 0.310]]) #inertia of link with respect to COM [kg*m^2]
    B1=0.02 #motor viscous friction  motor referred [Nm*s/rad]
    G1=12 #motor gear ratio [-]
    Jm1=0.000492 #motor inertia [kg*m^2]

    #Link2
    d2=0                                                                       
    a2=0.525                                                                      
    alpha2=0                                                                       
    m2=3.690                                                                      
    r2=np.array([-0.182, 0, 0])                                                               
    I2=np.array([[0, 0, 0],
                [0, 0, 0],
                [0, 0, 0.146]])                                                   
    B2=0.02                                                                  
    G2=9.33                                                                       
    Jm2=0.0004845   

    #Link 3
    d3=0                                                                        
    a3=0.370                                                                       
    alpha3=0                                                                       
    m3=2.565+(4-2.565)                                                             
    r3=np.array([-0.360, 0, 0])                                                                
    I3=np.array([[0, 0, 0],
                [0, 0, 0],
                [0, 0, 0.016]])                                                                                                                    
    B3=0.01
    G3=9.25                                                                        
    Jm3=0.0001859     

    #Payload
    pay_m = 1
    pay_I = 0
    pay_r = [.1, 0] #only 3 link ready for Yoffset of CoM!!
    
    #Link 4  
    m4=pay_m
    r4=np.array([0, 0, 0])
    a4 = pay_r[0]
    I4=np.array([[0, 0, 0],
                [0, 0, 0],
                [0, 0, pay_I]])                                                        

    #Links
    L1 = DHLink(d=d1, a=a1, alpha=alpha1, m=m1, r=r1, I=I1, B=B1, G=G1, Jm=Jm1)
    L2 = DHLink(d=d2, a=a2, alpha=alpha2, m=m2, r=r2, I=I2, B=B2, G=G2, Jm=Jm2)
    L3 = DHLink(d=d3, a=a3, alpha=alpha3, m=m3, r=r3, I=I3, B=B3, G=G3, Jm=Jm3)
    L4 = DHLink(a=a4, m=m4, r=r4, I=I4)

    #RTB Robots
    robot_1L = DHRobot([L1])
    robot_2L = DHRobot([L1, L2])
    robot_3L = DHRobot([L1, L2, L3])
    robot_4L = DHRobot([L1, L2, L3, L4])
    
    #Gravity
    gravity = 9.81
    robot_2L.gravity = [0, -gravity, 0]
    robot_3L.gravity = [0, -gravity, 0]
    robot_4L.gravity = [0, -gravity, 0]

    #PlanarRobots, Create robot from links
    robot_1link = OneLinkRobot(link1=L1, pay_m=pay_m, pay_I=pay_I, pay_r=pay_r, gravity=0)
    robot_2link = TwoLinkRobot(link1=L1, link2=L2, pay_m=pay_m, pay_I=pay_I, pay_r=pay_r, gravity=gravity)
    robot_3link = ThreeLinkRobot(link1=L1, link2=L2, link3=L3, pay_m=0, pay_I=0, pay_r=[0, 0], gravity=gravity)
    robot_3link_pay = ThreeLinkRobot(link1=L1, link2=L2, link3=L3, pay_m=pay_m, pay_I=pay_I, pay_r=pay_r, gravity=gravity)
    
    #Results 1 Link
    t = np.linspace(0, 1, 50)
    tg = quintic(0, 1, t)
    print(tg.q)
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau0 = robot_1link.tau(q, qd, qdd)
    tau1 = robot_1L.rne_python(q, qd, qdd)
    
    plt.figure()
    plt.plot(t, tau0,'.')
    plt.plot(t, tau1)
    plt.xlabel('time - [s]')
    plt.ylabel('joint torque - [Nm]')
    plt.title('1Link')
    plt.legend(['J1 Analytical', 'J1 RBT'])

    #Result 2 Link
    t = np.linspace(0, 1, 50)
    tg = jtraj([0, 0], [1, 1], t)
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau2 = robot_2link.tau(q, qd, qdd)
    tau3 = robot_2L.rne_python(q, qd, qdd)
    
    plt.figure()
    plt.plot(t, tau2,'.')
    plt.plot(t, tau3)
    plt.xlabel('time - [s]')
    plt.ylabel('joint torque - [Nm]')
    plt.title('2Link')
    plt.legend(['J1 Analytical','J2 Analytical', 'J1 RBT', 'J2 RBT'])
    
    #Result 3 Link
    t = np.linspace(0, 1, 50)
    tg = jtraj([0, 0, 0], [1, 1, 1], t) #set the 4 DUMMY DoF of the payload!!!!!
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau4 = robot_3link.tau(q, qd, qdd)
    tg = jtraj([0, 0, 0], [1, 1, 1], t)
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau5 = robot_3L.rne_python(q, qd, qdd)
    
    plt.figure()
    plt.plot(t, tau4[:, :3],'.')
    plt.plot(t, tau5[:, :3])
    plt.xlabel('time - [s]')
    plt.ylabel('joint torque - [Nm]')
    plt.title('3Link')
    plt.legend(['J1 Analytical','J2 Analytical','J3 Analytical', 'J1 RBT', 'J2 RBT', 'J3 RBT'])
    
    #result 3 link + payload
    t = np.linspace(0, 1, 50)
    tg = jtraj([0, 0, 0], [1, 1, 1], t) #set the 4 DUMMY DoF of the payload!!!!!
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau6 = robot_3link_pay.tau(q, qd, qdd)
    tg = jtraj([0, 0, 0, 0], [1, 1, 1, 0], t) #set the 4 DUMMY DoF of the payload!!!!!
    q, qd, qdd = transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau7 = robot_4L.rne_python(q, qd, qdd)

    plt.figure()
    plt.plot(t, tau6[:, :3],'.')
    plt.plot(t, tau7[:, :3])
    plt.xlabel('time - [s]')
    plt.ylabel('joint torque - [Nm]')
    plt.title('3Link + Payload')
    plt.legend(['J1 Analytical','J2 Analytical','J3 Analytical', 'J1 RBT', 'J2 RBT', 'J3 RBT'])

    plt.figure()
    plt.plot(t,tg.q[:,2],'.-')
    plt.plot(t,tg.qd[:,2],'.-')
    plt.plot(t,tg.qdd[:,2],'.-')
    plt.xlabel('time - [s]')
    plt.ylabel('[rad], [rad/s], [rad/s^2]')
    plt.legend(['J3 distance', 'J3 velocity', 'J3 acceleration'])
    plt.show()

if __name__ == "__main__":
    main()
