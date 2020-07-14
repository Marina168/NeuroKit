# -*- coding: utf-8 -*-
import numpy as np
import scipy.signal
import matplotlib.pyplot as plt

from ..signal.signal_detrend import signal_detrend


def signal_timefrequency(signal, sampling_rate=1000, min_frequency=0.04, max_frequency=np.inf, method="stft", window=None, nfreqbin=None, overlap=None, show=True):
    """Quantify changes of a nonstationary signal’s frequency over time.
    The objective of time-frequency analysis is to offer a more informative description of the signal
    which reveals the temporal variation of its frequency contents.

    There are many different Time-Frequency Representations (TFRs) available:

    - Linear TFRs: efficient but create tradeoff between time and frequency resolution
        - Short Time Fourier Transform (STFT): the time-domain signal is windowed into short segments
        and FT is applied to each segment, mapping the signal into the TF plane. This method assumes
        that the signal is quasi-stationary (stationary over the duration of the window). The width
        of the window is the trade-off between good time (requires short duration window) versus good
        frequency resolution (requires long duration windows)
        - Wavelet Transform (WT): similar to STFT but instead of a fixed duration window functrion, a
        varying window length by scaling the axis of the window is used. At low frequency, WT proves
        high spectral resolution but poor temporal resolution. On the other hand, for high frequencies,
        the WT provides high temporal resolution but poor spectral resolution.

    - Quadratic TFRs: better resolution but computationally expensive and suffers from having
    cross terms between multiple signal components
        - Wigner Ville Distribution (WVD): while providing very good resolution in time and frequency
        of the underlying signal structure, because of its bilinear nature, existence of negative values,
        the WVD has misleading TF results in the case of multi-component signals such as EEG due to the
        presence of cross terms and inference terms. Cross WVD terms can be reduced by using moothing kernal
        functions as well as analyzing the analytic signal (instead of the original signal)
        - Smoothed Pseudo Wigner Ville Distribution (SPWVD): to address the problem of cross-terms
        suppression, SPWVD allows two independent analysis windows, one in time and the other in frequency
        domains.

    Parameters
    ----------
    signal : Union[list, np.array, pd.Series]
        The signal (i.e., a time series) in the form of a vector of values.
    sampling_rate : int
        The sampling frequency of the signal (in Hz, i.e., samples/second).
    method : str
        Time-Frequency decomposition method.
    min_frequency : float
        The minimum frequency.
    max_frequency : float
        The maximum frequency.
    window : int
        Length of each segment in seconds. If None (default), window will be automatically
        calculated. For stft method
    nfreqbin : int, float
        Number of frequency bins. If None (default), nfreqbin will be set to 0.5*sampling_rate.
    overlap : int
        Number of points to overlap between segments. If None, noverlap = nperseg // 8. Defaults to None.
        When specified, the Constant OverLap Add (COLA) constraint must be met.
    show : bool
        If True, will return two PSD plots.

    Returns
    -------
    frequency : np.array
        Frequency.
    time : np.array
        Time array.
    stft : np.array
        Short Term Fourier Transform. Time increases across its columns and frequency increases
        down the rows.
    Examples
    -------
    >>> import neurokit2 as nk
    >>> import numpy as np
    >>> data = nk.data("bio_resting_5min_100hz")
    >>> sampling_rate=100
    >>> peaks, info = nk.ecg_peaks(data["ECG"], sampling_rate=sampling_rate)
    >>> peaks = np.where(peaks == 1)[0]
    >>> rri = np.diff(peaks) / sampling_rate * 1000
    >>> desired_length = int(np.rint(peaks[-1]))
    >>> signal = nk.signal_interpolate(peaks[1:], rri, x_new=np.arange(desired_length))
    >>> f, t, stft = nk.signal_timefrequency(signal, sampling_rate, max_frequency=0.5, method="stft", show=True)
    >>> f, t, cwtm = nk.signal_timefrequency(signal, sampling_rate, max_frequency=0.5, method="cwt", show=True)
    """
    # Initialize empty container for results
    # Define window length
    if min_frequency == 0:
        min_frequency = 0.04  # sanitize lowest frequency to lf
    if max_frequency == np.inf:
        max_frequency = sampling_rate // 2  # nyquist

    # STFT
    if method.lower() in ["stft"]:
        if window is not None:
            nperseg = int(window * sampling_rate)
        else:
            # to capture at least 5 times slowest wave-length
            nperseg = int((2 / min_frequency) * sampling_rate)

        frequency, time, tfr = short_term_ft(
                signal,
                sampling_rate=sampling_rate,
                min_frequency=min_frequency,
                max_frequency=max_frequency,
                overlap=overlap,
                nperseg=nperseg,
                show=show
                )
    # CWT
    elif method.lower() in ["cwt", "wavelet"]:
        frequency, time, tfr = continuous_wt(
                signal,
                sampling_rate=sampling_rate,
                min_frequency=min_frequency,
                max_frequency=max_frequency,
                show=show
                )

    return frequency, time, tfr

# =============================================================================
# Short-Time Fourier Transform (STFT)
# =============================================================================


def short_term_ft(signal, sampling_rate=1000, min_frequency=0.04, max_frequency=np.inf, overlap=None, nperseg=None, show=True):
    """Short-term Fourier Transform.
    """

    # Check COLA
    if overlap is not None:
        if not scipy.signal.check_COLA(scipy.signal.hann(nperseg, sym=True), nperseg, overlap):
            raise ValueError("The Constant OverLap Add (COLA) constraint is not met")

    frequency, time, stft = scipy.signal.spectrogram(
        signal,
        fs=sampling_rate,
        window='hann',
        scaling='density',
        nperseg=nperseg,
        nfft=None,
        detrend=False,
        noverlap=overlap,
        mode="complex"
    )

    # Visualization

    if show is True:
        lower_bound = len(frequency) - len(frequency[frequency > min_frequency])
        f = frequency[(frequency > min_frequency) & (frequency < max_frequency)]
        z = stft[lower_bound:lower_bound + len(f)]

        fig = plt.figure()
        spec = plt.pcolormesh(time, f, np.abs(z),
                              cmap=plt.get_cmap("magma"))
        plt.colorbar(spec)
        plt.title('STFT Magnitude')
        plt.ylabel('Frequency (Hz)')
        plt.xlabel('Time (sec)')

        fig, ax = plt.subplots()
        for i in range(len(time)):
            ax.plot(f, np.abs(z[:, i]), label="Segment" + str(np.arange(len(time))[i] + 1))
        ax.legend()
        ax.set_title('Power Spectrum Density (PSD)')
        ax.set_ylabel('PSD (ms^2/Hz)')
        ax.set_xlabel('Frequency (Hz)')

    return frequency, time, stft

# =============================================================================
# Smooth Pseudo-Wigner-Ville Distribution
# =============================================================================


def smooth_pseudo_wvd(signal, sampling_rate=1000, freq_length=None, time_length=None, segment_step=1, nfreqbin=None, window_method="hamming"):
    """Smoothed Pseudo Wigner Ville Distribution

    Parameters
    ----------
    signal : Union[list, np.array, pd.Series]
        The signal (i.e., a time series) in the form of a vector of values.
    freq_length : np.array
        Lenght of frequency smoothing window.
    time_length: np.array
        Lenght of time smoothing window
    segment_step : int
        The step between samples in `time_array`. Default to 1.
    nfreqbin : int
        Number of Frequency bins

    Returns
    -------
    frequency_array : np.array
        Frequency array.
    time_array : np.array
        Time array.
    pwvd : np.array
        SPWVD. Time increases across its columns and frequency increases
        down the rows.
    References
    ----------
    J. M. O' Toole, M. Mesbah, and B. Boashash, (2008),
    "A New Discrete Analytic Signal for Reducing Aliasing in the
     Discrete Wigner-Ville Distribution", IEEE Trans.
     """

    # Define parameters
    N = len(signal)
    sample_spacing = 1 / sampling_rate
    if nfreqbin is None:
        nfreqbin = 300

    # Zero-padded signal to length 2N
    signal_padded = np.append(signal, np.zeros_like(signal))

    # DFT
    signal_fft = np.fft.fft(signal_padded)
    signal_fft[1: N-1] = signal_fft[1: N-1] * 2
    signal_fft[N:] = 0

    # Inverse FFT
    signal_ifft = np.fft.ifft(signal_fft)
    signal_ifft[N:] = 0

    # Make analytic signal
    signal = scipy.signal.hilbert(signal_detrend(signal_ifft))

    # Create smoothing windows in time and frequency
    if freq_length is None:
        freq_length = np.floor(N / 4.0)
        # Plus one if window length is not odd
        if freq_length % 2 == 0:
            freq_length += 1
    elif len(freq_length) % 2 == 0:
        raise ValueError("The length of frequency smoothing window must be odd.")

    if time_length is None:
        time_length = np.floor(N / 10.0)
        # Plus one if window length is not odd
        if time_length % 2 == 0:
            time_length += 1
    elif len(time_length) % 2 == 0:
        raise ValueError("The length of time smoothing window must be odd.")

    if window_method == "hamming":
        freq_window = scipy.signal.hamming(int(freq_length))  # normalize by max
        time_window = scipy.signal.hamming(int(time_length))  # normalize by max
    elif window_method == "gaussian":
        std_freq = freq_length / (6 * np.sqrt(2 * np.log(2)))
        freq_window = scipy.signal.gaussian(freq_length, std_freq)
        freq_window /= max(freq_window)
        std_time = time_length / (6 * np.sqrt(2 * np.log(2)))
        time_window = scipy.signal.gaussian(time_length, std_time)
        time_window /= max(time_window)
    # to add warning if method is not one of the supported methods

    # Mid-point index of windows
    midpt_freq = (len(freq_window) - 1) // 2
    midpt_time = (len(time_window) - 1) // 2

    # Create arrays
    time_array = np.arange(start=0, stop=N, step=segment_step, dtype=int)
#    frequency_array = np.fft.fftfreq(nfreqbin, sample_spacing)[0:nfreqbin / 2]
    frequency_array = 0.5 * np.arange(nfreqbin, dtype=float) / N
    pwvd = np.zeros((nfreqbin, len(time_array)), dtype=complex)

    # Calculate pwvd
    for i, t in enumerate(time_array):
        # time shift
        tau_max = np.min([t + midpt_time - 1,
                          N - t + midpt_time,
                          np.round(N / 2.0) - 1,
                          midpt_freq])
        # time-lag list
        tau = np.arange(start=-np.min([midpt_time, N - t]),
                        stop=np.min([midpt_time, t - 1]) + 1,
                        dtype='int')
        time_pts = (midpt_time + tau).astype(int)
        g2 = time_window[time_pts]
        g2 = g2 / np.sum(g2)
        signal_pts = (t - tau - 1).astype(int)
        # zero frequency
        pwvd[0, i] = np.sum(g2 * signal[signal_pts] * np.conjugate(signal[signal_pts]))
        # other frequencies
        for m in range(int(tau_max)):
            tau = np.arange(start=-np.min([midpt_time, N - t - m]),
                            stop=np.min([midpt_time, t - m - 1]) + 1,
                            dtype='int')
            time_pts = (midpt_time + tau).astype(int)
            g2 = time_window[time_pts]
            g2 = g2 / np.sum(g2)
            signal_pt1 = (t + m - tau - 1).astype(int)
            signal_pt2 = (t - m - tau - 1).astype(int)
            # compute positive half
            rmm = np.sum(g2 * signal[signal_pt1] * np.conjugate(signal[signal_pt2]))
            pwvd[m + 1, i] = freq_window[midpt_freq + m + 1] * rmm
            # compute negative half
            rmm = np.sum(g2 * signal[signal_pt2] * np.conjugate(signal[signal_pt1]))
            pwvd[nfreqbin - m - 1, i] = freq_window[midpt_freq - m + 1] * rmm

        m = np.round(N / 2.0)

        if t <= N - m and t >= m + 1 and m <= midpt_freq:
            tau = np.arange(start=-np.min([midpt_time, N - t - m]),
                            stop=np.min([midpt_time, t - 1 - m]) + 1,
                            dtype='int')
            time_pts = (midpt_time + tau + 1).astype(int)
            g2 = time_window[time_pts]
            g2 = g2 / np.sum(g2)
            signal_pt1 = (t + m - tau).astype(int)
            signal_pt2 = (t - m - tau).astype(int)
            x = np.sum(g2 * signal[signal_pt1] * np.conjugate(signal[signal_pt2]))
            x *= freq_window[midpt_freq + m + 1]
            y = np.sum(g2 * signal[signal_pt2] * np.conjugate(signal[signal_pt1]))
            y *= freq_window[midpt_freq - m + 1]
            pwvd[m, i] = 0.5 * (x + y)

    pwvd = np.real(np.fft.fft(pwvd, axis=0))

    # Visualization

    return frequency_array, time_array, pwvd

# =============================================================================
# Continuous Wavelet Transform (CWT) - Morlet
# =============================================================================


def continuous_wt(signal, sampling_rate=1000, min_frequency=0.04, max_frequency=np.inf, nfreqbin=None, show=True):
    """
    References
    ----------
    - Neto, O. P., Pinheiro, A. O., Pereira Jr, V. L., Pereira, R., Baltatu, O. C., & Campos, L. A. (2016).
    Morlet wavelet transforms of heart rate variability for autonomic nervous system activity.
    Applied and Computational Harmonic Analysis, 40(1), 200-206.

   - Wachowiak, M. P., Wachowiak-Smolíková, R., Johnson, M. J., Hay, D. C., Power, K. E.,
   & Williams-Bell, F. M. (2018). Quantitative feature analysis of continuous analytic wavelet transforms
   of electrocardiography and electromyography. Philosophical Transactions of the Royal Society A:
   Mathematical, Physical and Engineering Sciences, 376(2126), 20170250.
    """

    # central frequency
    w = 6.  # recommended

    if nfreqbin is None:
        nfreqbin = sampling_rate // 2

    # frequency
    freq = np.linspace(min_frequency, max_frequency, nfreqbin)

    # time
    time = np.arange(len(signal)) / sampling_rate
    widths = w * sampling_rate / (2 * freq * np.pi)

    # Mother wavelet = Morlet
    cwtm = scipy.signal.cwt(signal, scipy.signal.morlet2, widths, w=w)

    # Visualisation
    if show is True:
        plt.figure()
#        spec = plt.pcolormesh(time, freq, np.abs(cwtm), cmap='viridis', shading='gouraud')
        spec = plt.pcolormesh(time, freq, np.abs(cwtm),
                              cmap=plt.get_cmap("magma"))
        plt.colorbar(spec)
        plt.title('Continuous Wavelet Transform Magnitude')
        plt.ylabel('Frequency (Hz)')
        plt.xlabel('Time (sec)')

    return freq, time, cwtm
