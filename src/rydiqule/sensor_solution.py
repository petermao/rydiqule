"""
Bunch-like object use to store aspects of a solution when calling rydiule.solve()
Adds essential keys with "None" entries
"""
from __future__ import annotations
from typing import Optional, Tuple, Union

import copy

import numpy as np
from scipy.constants import c
import warnings

# have to import this way to prevent circular imports
from rydiqule import sensor_utils


class Solution(dict):
    """
    Manual implementation of a bunch object which fuctions as a dictionary with
    the ability to access elements.

    For now, little additional funcitonality exists
    on top of this, but some may be added in the future.
    """
    # common attributes
    rho: np.ndarray
    """numpy.ndarray : Solutions returned by the solver."""
    eta: Optional[float]
    """float, optional : Eta constant from the Cell.
    Not generally defined when using a Sensor."""
    kappa: Optional[float]
    """float, optional : Kappa constant from the Cell.
    Not generally defined when using a Sensor."""
    probe_tuple: Optional[Tuple[int, int]]
    """Coupling edge corresponding to probing field.
    Not generally defined when using a Sensor."""
    probe_freq: Optional[float]
    """Probing transition frequency, in rad/s.
    Not generally defined when using a Sensor."""
    probe_rabi: Optional[Union[float, np.ndarray]]
    """Probe Rabi frequency, in Mrad/s.
    Not generally defined when using a Sensor."""
    cell_length: Optional[float]
    """Optical path length of the medium, in meters.
    Not generally defined when using a Sensor."""
    beam_area: Optional[float]
    """Cross-sectional area of the probing beam, in square meters.
    Not generally defined when using a Sensor."""

    couplings: dict
    """dict : Dictionary of the couplings."""
    axis_labels: list[str]
    """list of str : Labels for the axes of scanned parameters.
    If doppler averaging but not summing, doppler dimensions are prepended."""
    axis_values: list
    """list : Value arrays corresponding to each axis.
    If doppler averaging but not summing, doppler classes in internal units are added."""
    rq_version: str
    """str : Version of rydiqule that created the Solution."""
    basis: list[str]
    """list of str: The list of density matrix elements in the order they appear in the solution.
    See :meth:`Sensor.basis` for details."""

    # doppler specific
    doppler_classes: Optional[np.ndarray]
    """numpy.ndarray, optional : Doppler classes used to perform the doppler average.
    Will be None if doppler averaging was not used."""

    # time_solver specific
    t: np.ndarray
    """numpy.ndarray : Times the solution is returned at, when using the time solver.
    Undefined otherwise."""
    init_cond: np.ndarray
    """numpy.ndarray : Initial conditions, when using the time solver.
    Undefined otherwise."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__dict__ = self

    def rho_ij(self, i: int, j: int) -> np.ndarray:
        """
        Gets the i,j element(s) of the density matrix solutions.

        See :func:`~.get_rho_ij` for details.

        Parameters
        ----------
        i: int
            density matrix element `i`
        j: int
            density matrix element `j`

        Returns
        -------
        numpy.ndarray
            `[i,j]` elments of the density matrix
        """

        return sensor_utils.get_rho_ij(self.rho, i, j)
    
    def get_solution_element(self, idx: int) -> np.ndarray:
        """
        Return a slice of an n_dimensional matrix of solutions of shape (...,n^2-1),
        where n is the basis size of the quantum system.

        Parameters
        ----------
        idx: int
            Solution index to slice.

        Returns
        -------
        numpy.ndarray
            Slice of solutions corresponding to index idx. For example,
            if sols has shape (..., n^2-1), sol_slice will have shape (...).

        Raises
        ------
        IndexError
            If `idx` in not within the shape determined by basis size.

        Examples
        --------
        >>> c = rq.Cell('Rb85', *rq.D2_states('Rb85'))
        >>> c.add_coupling(states=(0,1), rabi_frequency=1, detuning=1)
        >>> sols = rq.solve_steady_state(c)
        >>> print(sols.rho.shape)
        >>> rho_01_im = sols.get_solution_element(0)
        >>> print(rho_01_im)
        (3,)
        0.0013139903428765695

        """
        basis_size = np.sqrt(self.rho.shape[-1] + 1)
        try:
            sol_slice = self.rho.take(indices=idx, axis=-1)
        except IndexError:
            raise IndexError(f"No element with given index for {basis_size}-level system")

        return sol_slice
    
    def get_susceptibility(self) -> np.ndarray:
        """
        Return the atomic susceptibility on the probe transition.

        Experimental parameters must be defined manually for a `Sensor`.

        Returns
        -------
        numpy.ndarray
            Susceptibility of the density matrix solution.

        Examples
        --------
        >>> c = rq.Cell('Rb85', *rq.D2_states('Rb85'), cell_length = 0.0001)
        >>> c.add_coupling(states=(0,1), rabi_frequency=1, detuning=1)
        >>> sols = rq.solve_steady_state(c)
        >>> print(sols.rho.shape)
        >>> sus = sols.get_susceptibility()
        >>> print(sus)
        (3,)
        (1.9046090082907774e-05+0.0003680924230367812j)

        """
        #transition_frequency: Optional[float] = None
        
        self._variables_defined('probe_rabi', 'kappa', 'probe_freq')
            
        probe_rabi = self.probe_rabi*1e6 #rad/s
        kappa = self.kappa
        probe_freq = self.probe_freq

        # reverse probe tuple order to get correct sign of imag
        rho_probe = self.rho_ij(*self.probe_tuple[::-1])

        # See Steck for last factor of 2.  Comes from Steck QO Notes page
        return kappa * (rho_probe * 2*c) / (probe_freq * (probe_rabi/2))

    def get_OD(self) -> np.ndarray:
        """
        Calculates the optical depth from the solution.  This equation comes from
        Steck's Quantum Optics Notes Eq. 6.74.

        Assumes the optically-thin approximation is valid.
        If a calculated OD for a solution exceeds 1,
        this approximation is likely invalid.

        Returns
        -------
        OD: numpy.ndarray
            Optical depth of the sample

        Warns
        -----
        UserWarning
            If any OD exceeds 1, which indicates the optically-thin approximation
            is likely invalid.

        Examples
        --------
        >>> c = rq.Cell('Rb85', *rq.D2_states('Rb85'), cell_length =  0.01)
        >>> c.add_coupling(states=(0,1), rabi_frequency=1, detuning=1)
        >>> sols = rq.solve_steady_state(c)
        >>> print(sols.rho.shape)
        >>> OD = sols.get_OD()
        >>> print(OD)
        (3,)
        29.642013239786518
        ~/src/Rydiqule/src/rydiqule/sensor_solutions.py:103: UserWarning:
        At least one solution has optical depth greater than 1.
        Integrated results are likely invalid.

        """
        self._variables_defined('probe_freq', 'cell_length')

        probe_wavelength = np.abs(c/(self.probe_freq/(2*np.pi))) #meters
        probe_wavevector = 2*np.pi/probe_wavelength #1/meters
        OD = self.get_susceptibility().imag*self.cell_length*probe_wavevector
        if np.any(OD > 1.0):
            # optically-thin approximation probably violated
            warnings.warn(('At least one solution has optical depth '
                        'greater than 1. Integrated results are '
                        'likely invalid.'))

        return OD

    def get_transmission_coef(self) -> np.ndarray:
        """
        Extract the transmission term from a solution.

        Assumes the optically-thin approximation is valid.

        Returns
        -------
        numpy.ndarray
            Numerical value of the probe absorption in fractional units
            (P_out/P_in).

        Examples
        --------
        >>> c = rq.Cell('Rb85', *rq.D2_states('Rb85'), cell_length = 0.0001)
        >>> c.add_coupling(states=(0,1), rabi_frequency=0.1, detuning=0)
        >>> sols = rq.solve_steady_state(c)
        >>> print(sols.rho.shape)
        >>> t = sols.get_transmission_coef()
        >>> print(t)
        (3,)
        0.7425903081191148
        """
        
        OD = self.get_OD()
        transmission_coef = np.exp(-OD)
        return transmission_coef
    
    def get_phase_shift(self) -> np.ndarray:
        """
        Extract the phase shift from a solution.

        Assumes the optically-thin approximation is valid.

        Returns
        -------
        numpy.ndarray
            Probe phase in radians.

        Examples
        --------
        >>> c = rq.Cell('Rb85', *rq.D2_states('Rb85'), cell_length = .00001)
        >>> c.add_coupling(states=(0,1), rabi_frequency=1, detuning=1)
        >>> sols = rq.solve_steady_state(c)
        >>> print(sols.rho.shape)
        >>> phase_shift = sols.get_phase_shift()
        >>> print(phase_shift)
        (3,)
        80.52949114644437
        """
        self._variables_defined('probe_rabi', 'kappa', 'cell_length')
        
        # reverse probe tuple order to get correct sign of imag
        # not actually necessary for this function since only need real part
        susc = self.get_susceptibility()
        n_refrac = 1+susc.real/2 #steck Quantum Optics Notes eq 6.71
        wavelength = 2*np.pi*c/self.probe_freq
        wavevector = 2*np.pi/wavelength
        phaseshift = n_refrac*self.cell_length*wavevector

        return phaseshift

    def copy(self):
        return copy.copy(self)
    
    def deepcopy(self):
        return copy.deepcopy(self)
    
    def _variables_defined(self, *var_names):
        """Check if provided experimental parameter variables are defined.
        
        Parameters
        ----------
        var_names: str
            Parameter names to check if not None

        Raises
        ------
        AttributeError
            If one or more parameters are not defined.
        """

        undef_vars = []
        for var in var_names:
            if self[var] is None:
                undef_vars.append(var)
        
        if len(undef_vars):
            raise AttributeError(f'Required parameters not defined: {undef_vars}\n'
                                 'Please define in Sensor and redo calculation.')
                                 
