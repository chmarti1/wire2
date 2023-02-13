#!/usr/bin/python3
"""Spinning Disc Langmuir Probe (SDLP) spatial measurement utilities


"""

import numpy as np
from scipy.linalg import solve
import array,struct


class WireSlice(object):
    """WireSlice - ion densities in a 2D slice constructed from SDLP measurements

    ws = WireSlice(L, ...)
    
** L **
The domain size can be specified as a tuple for a rectuangular domain
    ws = WireSlice(L = (width, height), ...)
or with a scalar for a square domain
    ws = WireSlice(L = side, ...)

No length units are presumed, but all lengths used by WireSlice 
instances must be the same.  For display purposes, an optional unit 
string may be specified using the length keyword.  
    ws = WireSlice( ... units='mm', ...)
    
** Defining the Expansion **
The number of terms used in the Fourier expansion in x (horizontal) and
y (vertical) can be specified explicitly by N or implicitly by the 
highest wavenumber, k.  Either N or k is required.

** N **
The number of non-zero wavenumbers in each axis can be independently 
specified by a tuple,
    ws = WireSlice( ... N = (Nx, Ny), ...)
or with a scalar to specify them to be the same 
    ws = WireSlice( ... N = number, ...)

The total number of terms in the expansion is
    (Nx + 1) * (Ny + 1).
One is added to each dimension to include the constant term.

** k **
The maximum wavenumber is an alternative means for determining the number
of terms in the expansion.  A wavenumber is the spatial equivalent to a
frequency.  With units 1/length, it specifies the number of wave periods
in a unit length.  Therefore, the maximum wavenumber along an axis is 
k=N/L.

The maximum wavenumber can be specified for each axis in a tuple
    ws = WireSlice( ... k = (kx, ky), ...)
or with a scalar to specify them to be the same
    ws = WireSlice( ... k = number, ...)
    
The maximum wavenumber determines the tightest spatial gradient that can
be represented in the expansion.  The inverse of the maximum wavenumber
is a measure of the spatial resolution that can be represented by the
expansion.
"""
    
    def __init__(self, L, N=None, k=None, units=''):
        # Force L to be a two-element vector
        
        self.L = np.broadcast_to(np.asarray(L, dtype=int), (2,))
        self.N = np.zeros([2], dtype=int)   # number of wavenumbers
        self.units = str(units)


        if N is not None:
            if k is not None:
                raise Exception('Cannot specify both N and k simultaneously')
            self.N[:] = N
        elif k is not None:
            self.N[:] = np.floor(k/self.L)
        else:
            raise Exception('Either N or k must be specified.')
           
        self.ncoef = np.prod(2*self.N+1)

        # establish wavenumber vectors
        self.nu = np.meshgrid(
                np.arange(-self.N[0], self.N[0]+1)/self.L[0],
                np.arange(-self.N[1], self.N[1]+1)/self.L[1],
                indexing='ij', sparse=True)
        
        # initialize a solution matrix and vectors
        self.C = None
        self.I0 = None
        self.A = np.zeros((self.ncoef, self.ncoef), dtype=complex)
        self.B = np.zeros((self.ncoef,), dtype=complex)
        
        
    def __call__(self, x, y):
        # To be written
        pass
        
    def lam(self, r, d, theta):
        """LAM - calculate the lambda vector for a given d and theta
"""
        # Does this theta actually intersect the domain?
        theta_critical = np.arctan(self.L[1] / (2*d))
        if not -theta_critical < theta < theta_critical or r<=d:
            LAM = np.zeros((self.ncoef,),dtype=complex)
            #LAM[self.flatindex(0,0)] = 1.0j
            return LAM
   
        # Sines and cosines will come in handy repeatedly
        sth = np.sin(theta)
        cth = np.cos(theta)
        
        # Calculate R1
        # Since these raidii calculations can be infinite, first calculate
        # the maximum inverse of radius, which will never be zero.
        # Then, we'll invert it again.
        r1 = 1./max(1./r, 
                cth/(self.L[0] + d), 
                np.abs(2*sth/self.L[1]))
                
        # Calculate R0
        r0 = d/cth

        # Calculate a wavenumber matrix
        nu = self.nu[0]*cth + self.nu[1]*sth
        # Izero is a boolean index marking elements where k is zero
        Izero = (nu == 0)
        # Force k to a non-zero number
        nu[Izero] = -1
        
        # Calculate the line integral matrix
        gam = (np.exp(2j*np.pi*nu*r1) - np.exp(2j*np.pi*nu*r0)) / (2j*np.pi*nu)
        # Handle the special m=n=0 case
        gam[Izero] = r1-r0
        # gam is now the "gamma" value described in the paper.  We will
        # now, further modify the variable by the d-exponential 
        LAM = (np.exp(-2j*np.pi*self.nu[0]*d) * gam).flatten()
        # Modify the constant term to include the offset current as its
        # imaginary part
        #LAM[self.flatindex(0,0)] += 1j
        
        return LAM

    def flatindex(self, m, n):
        return np.ravel_multi_index(self.N+[m,n], 2*self.N+1)

    def mnindex(self, index):
        return np.unravel_index(index, 2*self.N+1)-self.N

    def include(self, r, d, theta, I):
        """INCLUDE - include a datum in the model
    include(r, d, theta, I)
    
d   -   distance between the center of rotation and the domain edge
theta - the wire angle in radians
I   -   The total current measured in this position
"""
        lam = self.lam(r, d, theta)
        self.A += lam.reshape((lam.size,1)) * lam
        self.B += I * lam

    def read(self, filename):
        """Read from a file
    ws.read(filename)
        OR
    ws.read(wf)
    
Reads from a file or from an open WireFile instance
"""
        if isinstance(filename,str):
            wf = WireFile(filename)
            with wf.open('r'):
                self.read(wf)
            return
        elif not isinstance(filename,WireFile):
            raise Exception('The file must be either a string path or a WireFile instance.')
        
        for r,d,theta,I in filename:
            self.include(r,d,theta,I)
            
        
    def solve(self):
        """SOLVE - solve the system with the data already included
"""
        self.C = solve(self.A, self.B, assume_a='sym')
        #self.C = solve(self.A, self.B)
        
        # Grab the offset current
        self.I0 = self.C[self.flatindex(0,0)].imag


    def grid(self,Nx=None, Ny=None):
        """GRID - evaluate the solution at grid points
    x,y,I = grid()
        OR
    x,y,I = grid(N)
        Or
    x,y,I = grid(Nx, Ny)
    
If no argument is given, the grid spacing is selected automatically 
based on the highest wave number in each axis.  If a single scalar 
argument is given, it is treated as the number of grid oints in each
axis.  If tuple pair of arguments are found, they are interpreted as 
the number of grid points in the x- and y-axes.
"""
        # If no arguments are given
        if Nx is None:
            if Ny is None:
                Nx,Ny = 2*self.N+1
            else:
                raise Exception('Cannot specify Ny without specifying Nx.')
        # If Nx is given
        elif Ny is None:
            Ny = Nx
        # If Nx and Ny are given, do nothing        
        x = np.linspace(0,self.L[0],Nx)
        y = np.linspace(-self.L[1]/2, self.L[1]/2, Ny)
        x,y = np.meshgrid(x,y)
        return x,y

class WireFile:
    def __init__(self, filename):
        self.filename = filename
        self.fd = None
        self.isread = False
        self.lineformat = '@dddd'
        self.linebytes = struct.calcsize(self.lineformat)

    def open(self, mode):
        if self.fd is not None:
            raise FileExistsError('File is already open.')
        if mode in ['r', 'rb']:
            self.fd = open(self.filename, 'rb')
            self.isread = True
        elif mode in ['w', 'wb']:
            self.fd = open(self.filename, 'wb')
            self.isread = False
        elif mode in ['a', 'ab']:
            self.fd = open(self.filename, 'ab')
            self.isread = False
        elif mode in ['x', 'xb']:
            self.fd = open(self.filename, 'xb')
            self.isread = False
        return self
    
    def close(self):
        if self.fd is None:
            raise FileExistsError('File is already closed.')
        self.fd.close()
        self.fd = None
        self.isread = False
        
    def __enter__(self):
        return self
        
    def __iter__(self):
        if not self.isread:
            raise Exception('The file is not opened in read mode.')
        return self
    
    def __next__(self):
        bb = self.fd.read(self.linebytes)
        if len(bb) < self.linebytes:
            raise StopIteration
        return struct.unpack(self.lineformat, bb)
        
    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.fd is not None:
            self.fd.close()
            self.fd = None
            self.isread = False
        return False

    def readline(self):
        if self.isread:
            bb = self.fd.read(self.linebytes)
            if len(bb) < self.linebytes:
                return ()
            return struct.unpack(self.lineformat, bb)
        raise Exception('The file is not opened in read mode.')
        
    def writeline(self, r, d, theta, I):
        """Write a single radius, diameter, angle, and current entry to the file
        
    with wf.open('w'):
        wf.writeline(r,d,theta,I)
"""
        if self.isread or self.fd is None:
            raise Exception('The file is not opened in write mode.')
        self.fd.write(struct.pack(self.lineformat, r,d,theta,I))

