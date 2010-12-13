import numpy as np
from .. import family, snapshot, units, array


#
# A module for making profiles of particle properties
#


class Profile:
    """

    A basic profile class for arbitrary profiles. Stores information about bins etc.

    Made to work with the pynbody SimSnap instances. The constructor only
    generates the bins and figures out which particles belong in which bin. 
    Profiles are generated lazy-loaded when a given property is requested.

    Input:

    sim : a simulation snapshot - this can be any subclass of SimSnap

    Optional Keywords:

    ndim (default = 2): specifies whether it's a 2D or 3D profile - in the
                       2D case, the bins are generated in the xy plane

    type (default = 'lin'): specifies whether bins should be spaced linearly ('lin'),
                            logarithmically ('log') or contain equal numbers of
                            particles ('equaln')

    min (default = min(x)): minimum value to consider
    max (default = max(x)): maximum value to consider
    nbins (default = 100): number of bins


    Output:

    a Profile object. To find out which profiles are available, use keys().
    The class defines  __get__ and __getitem__ methods so that
    these are equivalent:

    p.mass == p['mass'] # AP - *Must* we have this? p['mass'] seems quite sufficient to me

    Implemented profile functions:

    den: density
    fourier: provides fourier coefficients, amplitude and phase for m=0 to m=6.
             To access the amplitude profile of m=2 mode, do
             >>> p.fourier['amp'][2,:]
             


    Additional functions should use the profile_property to
    yield the desired profile. For example, to generate the density
    profile, all that is required is

    >>> p = profile(sim)
    >>> p.den
    

    Examples:

    >>> s = pynbody.load('mysim')
    >>> import pynbody.profile as profile
    >>> p = profile.Profile(s) # 2D profile of the whole simulation - note
                               # that this only makes the bins etc. but
                               # doesn't generate the density
    >>> p.den # now we have a density profile
    >>> p.keys()
    ['mass', 'n', 'den']
    >>> p.families()
    [<Family dm>, <Family star>, <Family gas>]
    
    >>> ps = profile.Profile(s.s) # xy profile of the stars
    >>> ps = profile.Profile(s.s, type='log') # same, but with log bins
    >>> ps.families()
    [<Family star>]
    >>> import matplotlib.pyplot as plt
    >>> plt.plot(ps.r, ps.den, 'o')
    >>> plt.semilogy()


    """

    _profile_registry = {}
    
    def __init__(self, sim, ndim = 2, type = 'lin', **kwargs):


        self._ndim = ndim
        self._type = type
        self._sim = sim

        x = ((sim['pos'][:,0:ndim]**2).sum(axis = 1))**(1,2)
        self._x = x

        # The profile object is initialized given some array of values
        # and optional keyword parameters

        if kwargs.has_key('max'):
            self.max = kwargs['max']
        else:
            self.max = np.max(x)
        if kwargs.has_key('nbins'):
            self.nbins = kwargs['nbins']
        else:
            self.nbins = 100
            
        if kwargs.has_key('min'):
            self.min = kwargs['min']
        else:
            self.min = np.min(x[x>0])

        if type == 'log':
            self.bins = np.logspace(np.log10(self.min), np.log10(self.max), num = self.nbins+1)
        elif type == 'lin':
            self.bins = np.linspace(self.min, self.max, num = self.nbins+1)
        elif type == 'equaln':
            raise RuntimeError, "Equal-N bins not implemented yet"
        else:
            raise RuntimeError, "Bin type must be one of: lin, log, equaln"
            

        self.bins = array.SimArray(self.bins, x.units)

        self.n, bins = np.histogram(self._x, self.bins)

        # middle of the bins for convenience
        
        self.r = 0.5*(self.bins[:-1]+self.bins[1:])

        self.binind = []

        self.partbin = np.digitize(self._x, self.bins)
        
        
        assert ndim in [2,3]
        if ndim == 2:
            self._binsize = np.pi*(self.bins[1:]**2 - self.bins[:-1]**2)
        else:
            self._binsize  = 4./3.*np.pi*(self.bins[1:]**3 - self.bins[:-1]**3)
            
        for i in np.arange(self.nbins)+1:
            ind = np.where(self.partbin == i)
            self.binind.append(ind)
            
        # set up the empty list of profiles
        self._profiles = {'n':self.n}


    def __len__(self):
        """Returns the number of bins used in this profile object"""
        return self.nbins
    

    def _get_profile(self, name) :
	"""Return the profile of a given kind"""
	if name in self._profiles :
	    return self._profiles[name]
	elif name in Profile._profile_registry :
	    self._profiles[name] = Profile._profile_registry[name](self)
	    return self._profiles[name]
	else :
	    raise KeyError, name+" is not a valid profile"
	
    def __getitem__(self, name):
        """Return the profile of a given kind"""
        return self._get_profile(name)

    def __delitem__(self, name) :
	del self._profiles[name]

	
	
    def __getattr__(self, name) :
	# AP - I don't like this, implementing for consistency with Rok's ideas only.
	try:
	    return self._get_profile(name)
	except KeyError :
	    raise AttributeError(name)

    def __delattr__(self, name) :
	# AP - I don't like this, implementing for consistency with Rok's ideas only.
	del self._profiles[name]


    def __repr__(self):
        return ("<Profile: " +
                str(self.families()) + " ; " +
                str(self._ndim) + "D ; " + 
                self._type) + " ; " + str(self.keys())+ ">"

    def keys(self):
        """Returns a listing of available profile types"""
        return self._profiles.keys()


    def families(self):
        """Returns the family of particles used"""
        return self._sim.families()



    @staticmethod
    def profile_property(fn) :
	Profile._profile_registry[fn.__name__]=fn
	return fn
    

@Profile.profile_property
def mass(self):
    """
    Calculate mass in each bin
    """

    #print '[calculating mass]'
    mass = np.zeros(self.nbins)
    for i in range(self.nbins):
	mass[i] = (self._sim['mass'][self.binind[i]]).sum()
    return mass

@Profile.profile_property
def den(self):
    """
    Generate a radial density profile for the current type of profile
    """

    #print '[calculating density]'
    return self.mass/self._binsize

@Profile.profile_property
def fourier(self):
    """
    Generate a profile of fourier coefficients, amplitudes and phases
    """
    #print '[calculating fourier decomposition]'
    from . import fourier_decomp
    
    f = {'c': np.zeros((7, self.nbins),dtype=complex),
	 'amp': np.zeros((7, self.nbins)),
	 'phi': np.zeros((7, self.nbins))}

    for i in range(self.nbins):
	if self.n[i] > 100:
	    f['c'][:,i] = fourier_decomp.fourier(self._sim['x'][self.binind[i]],
						 self._sim['y'][self.binind[i]],
						 self._sim['mass'][self.binind[i]])


    f['c'][:,self.mass>0] /= self.mass[self.mass>0]
    f['amp'] = np.sqrt(np.imag(f['c'])**2 + np.real(f['c'])**2)
    f['phi'] = np.arctan2(np.imag(f['c']), np.real(f['c']))

    return f

@Profile.profile_property
def mass_enc(self):
    """
    Generate the enclosed mass profile
    """
    m_enc = array.SimArray(np.zeros(self.nbins), 'Msol')
    for i in range(self.nbins):
        m_enc[i] = self.mass[:i].sum()
    return m_enc

@Profile.profile_property
def rotation_curve(self):
    """
    Generate a simple rotation curve: vc = sqrt(G M_enc/r)
    """

    print 'THIS GIVES WRONG VALUES'

    G = array.SimArray(1.0,units.G,dtype=float)
    return ((G*self.mass_enc/self.r)**(1,2)).in_units('km s**-1')

@Profile.profile_property
def vr(self):
    """
    Generate a mean radial velocity profile, where the vr vector
    is taken to be in three dimensions - for in-plane radial velocity
    use the vr_xy array.
    """
    vr = np.zeros(self.nbins)
    for i in range(self.nbins):
        vr[i] = (self._sim['vr'][self.binind[i]]*self._sim['mass'][self.binind[i]]).sum()
    vr /= self['mass']
    return vr

@Profile.profile_property
def vrxy(self):
    """
    Generate a mean radial velocity profile, where the vr vector
    is taken to be in three dimensions - for in-plane radial velocity
    use the vr_xy array.
    """
    vrxy = np.zeros(self.nbins)
    for i in range(self.nbins):
        vrxy[i] = (self._sim['vrxy'][self.binind[i]]*self._sim['mass'][self.binind[i]]).sum()
    vrxy /= self['mass']
    return vrxy
