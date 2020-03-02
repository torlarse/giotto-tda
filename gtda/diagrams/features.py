"""Feature extraction from persistence diagrams."""
# License: GNU AGPLv3

import numbers
import types

import numpy as np
from joblib import Parallel, delayed, effective_n_jobs
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils import gen_even_slices
from sklearn.utils.validation import check_is_fitted

from ._metrics import betti_curves, landscapes, heats,\
    persistence_images, silhouettes
from ._utils import _subdiagrams, _bin, _calculate_weights
from ..utils._docs import adapt_fit_transform_docs
from ..utils.validation import validate_params, check_diagram


@adapt_fit_transform_docs
class PersistenceEntropy(BaseEstimator, TransformerMixin):
    """`Persistence entropies <https://giotto.ai/theory>`_ of persistence
    diagrams.

    Given a persistence diagrams consisting of birth-death-dimension triples
    [b, d, q], subdiagrams corresponding to distinct homology dimensions are
    considered separately, and their respective persistence entropies are
    calculated as the (base e) entropies of the collections of differences
    d - b, normalized by the sum of all such differences.

    Parameters
    ----------
    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1 unless
        in a :obj:`joblib.parallel_backend` context. ``-1`` means using all
        processors.

    Attributes
    ----------
    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`, sorted in ascending order.

    See also
    --------
    BettiCurve, PersistenceLandscape, HeatKernel, Amplitude, \
    PersistenceImage, PairwiseDistance, Silhouette, \
    gtda.homology.VietorisRipsPersistence

    """

    def __init__(self, n_jobs=None):
        self.n_jobs = n_jobs

    def _persistence_entropy(self, X):
        X_lifespan = X[:, :, 1] - X[:, :, 0]
        X_normalized = X_lifespan / np.sum(X_lifespan, axis=1).reshape(-1, 1)
        return - np.sum(np.nan_to_num(
            X_normalized * np.log(X_normalized)), axis=1).reshape(-1, 1)

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_`. Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)

        self.homology_dimensions_ = sorted(set(X[0, :, 2]))
        self._n_dimensions = len(self.homology_dimensions_)

        return self

    def transform(self, X, y=None):
        """Compute the persistence entropies of diagrams in `X`.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions)
            Persistence entropies: one value per sample and per homology
            dimension seen in :meth:`fit`. Index i along axis 1 corresponds
            to the i-th homology dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X)

        with np.errstate(divide='ignore', invalid='ignore'):
            Xt = Parallel(n_jobs=self.n_jobs)(
                delayed(self._persistence_entropy)(_subdiagrams(X, [dim])[s])
                for dim in self.homology_dimensions_
                for s in gen_even_slices(
                    X.shape[0], effective_n_jobs(self.n_jobs))
            )
        Xt = np.concatenate(Xt).reshape(self._n_dimensions, X.shape[0]).T
        return Xt


@adapt_fit_transform_docs
class BettiCurve(BaseEstimator, TransformerMixin):
    """`Betti curves <https://giotto.ai/theory>`_ of persistence diagrams.

    Given a persistence diagram consisting of birth-death-dimension triples
    [b, d, q], subdiagrams corresponding to distinct homology dimensions are
    considered separately, and their respective Betti curves are obtained by
    evenly sampling the `filtration parameter <https://giotto.ai/theory>`_.

    Parameters
    ----------
    n_bins : int, optional, default: ``100``
        The number of filtration parameter values, per available homology
        dimension, to sample during :meth:`fit`.

    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1
        unless in a :obj:`joblib.parallel_backend` context. ``-1`` means
        using all processors.

    Attributes
    ----------
    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`, sorted in ascending order.

    samplings_ : dict
        For each number in `homology_dimensions_`, a discrete sampling of
        filtration parameters, calculated during :meth:`fit` according to the
        minimum birth and maximum death values observed across all samples.

    See also
    --------
    PersistenceLandscape, PersistenceEntropy, HeatKernel, Amplitude, \
    PairwiseDistance, Silhouette, PersistenceImage,\
    gtda.homology.VietorisRipsPersistence

    Notes
    -----
    The samplings in :attr:`samplings_` are in general different between
    different homology dimensions. This means that the j-th entry of a Betti
    curve in homology dimension q typically arises from a different parameter
    values to the j-th entry of a curve in dimension q'.

    """

    _hyperparameters = {'n_bins': [int, (1, np.inf)]}

    def __init__(self, n_bins=100, n_jobs=None):
        self.n_bins = n_bins
        self.n_jobs = n_jobs

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_` and, for each dimension separately,
        store evenly sample filtration parameter values in :attr:`samplings_`.
        Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)
        validate_params(self.get_params(), self._hyperparameters)

        self.homology_dimensions_ = sorted(list(set(X[0, :, 2])))
        self._n_dimensions = len(self.homology_dimensions_)

        self._samplings, _ = _bin(X, metric='betti', n_bins=self.n_bins)
        self.samplings_ = {dim: s
                           for dim, s in self._samplings.items()}
        return self

    def transform(self, X, y=None):
        """Compute the Betti curves of diagrams in `X`.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions, n_bins)
            Betti curves: one curve (represented as a one-dimensional array
            of integer values) per sample and per homology dimension seen
            in :meth:`fit`. Index i along axis 1 corresponds to the i-th
            homology dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X)

        Xt = Parallel(n_jobs=self.n_jobs)(delayed(betti_curves)(
                _subdiagrams(X, [dim], remove_dim=True)[s],
                self._samplings[dim])
            for dim in self.homology_dimensions_
            for s in gen_even_slices(X.shape[0],
                                     effective_n_jobs(self.n_jobs)))
        Xt = np.concatenate(Xt).\
            reshape(self._n_dimensions, X.shape[0], -1).\
            transpose((1, 0, 2))
        return Xt


@adapt_fit_transform_docs
class PersistenceLandscape(BaseEstimator, TransformerMixin):
    """`Persistence landscapes <https://giotto.ai/theory>`_ of persistence
    diagrams.

    Given a persistence diagram consisting of birth-death-dimension triples
    [b, d, q], subdiagrams corresponding to distinct homology dimensions are
    considered separately, and layers of their respective persistence
    landscapes are obtained by evenly sampling the `filtration parameter
    <https://giotto.ai/theory>`_.

    Parameters
    ----------
    n_layers : int, optional, default: ``1``
        How many layers to consider in the persistence landscape.

    n_bins : int, optional, default: ``100``
        The number of filtration parameter values, per available
        homology dimension, to sample during :meth:`fit`.

    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1 unless
        in a :obj:`joblib.parallel_backend` context. ``-1`` means using all
        processors.

    Attributes
    ----------
    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`.

    samplings_ : dict
        For each number in `homology_dimensions_`, a discrete sampling of
        filtration parameters, calculated during :meth:`fit` according to the
        minimum birth and maximum death values observed across all samples.

    See also
    --------
    BettiCurve, PersistenceEntropy, HeatKernel, Amplitude, \
    PairwiseDistance, Silhouette, PersistenceImage, \
    gtda.homology.VietorisRipsPersistence

    Notes
    -----
    The samplings in :attr:`samplings_` are in general different between
    different homology dimensions. This means that the j-th entry of the
    k-layer of a persistence landscape in homology dimension q typically
    arises from a different parameter value to the j-th entry of a k-layer in
    dimension q'.

    """

    _hyperparameters = {'n_layers': [int, (1, np.inf)],
                        'n_bins': [int, (1, np.inf)]}

    def __init__(self, n_layers=1, n_bins=100, n_jobs=None):
        self.n_layers = n_layers
        self.n_bins = n_bins
        self.n_jobs = n_jobs

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_` and, for each dimension separately,
        store evenly sample filtration parameter values in :attr:`samplings_`.
        Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)
        validate_params(self.get_params(), self._hyperparameters)

        self.homology_dimensions_ = sorted(list(set(X[0, :, 2])))
        self._n_dimensions = len(self.homology_dimensions_)

        self._samplings, _ = _bin(X, metric="landscape", n_bins=self.n_bins)
        self.samplings_ = {dim: s
                           for dim, s in self._samplings.items()}

        return self

    def transform(self, X, y=None):
        """Compute the persistence landscapes of diagrams in `X`.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions, \
            n_layers, n_bins)
            Persistence lanscapes: one landscape (represented as a
            two-dimensional array) per sample and per homology dimension seen
            in :meth:`fit`. Each landscape contains a number `n_layers` of
            layers. Index i along axis 1 corresponds to the i-th homology
            dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X)

        Xt = Parallel(n_jobs=self.n_jobs)(delayed(landscapes)(
                _subdiagrams(X, [dim], remove_dim=True)[s],
                self._samplings[dim],
                self.n_layers)
            for dim in self.homology_dimensions_
            for s in gen_even_slices(X.shape[0],
                                     effective_n_jobs(self.n_jobs)))
        Xt = np.concatenate(Xt).reshape(self._n_dimensions, X.shape[0],
                                        self.n_layers, self.n_bins).\
            transpose((1, 0, 2, 3))
        return Xt


@adapt_fit_transform_docs
class HeatKernel(BaseEstimator, TransformerMixin):
    """Convolution of persistence diagrams with a Gaussian kernel.

    Based on ideas in [1]_. Given a persistence diagram consisting of
    birth-death-dimension triples [b, d, q], subdiagrams corresponding to
    distinct homology dimensions are considered separately and regarded as sums
    of Dirac deltas. Then, the convolution with a Gaussian kernel is computed
    over a rectangular grid of locations evenly sampled from appropriate
    ranges of the `filtration parameter <https://giotto.ai/theory>`_. The
    same is done with the reflected images of the subdiagrams about the
    diagonal, and the difference between the results of the two convolutions is
    computed. The result can be thought of as a raster image.

    Parameters
    ----------
    sigma : float, optional default ``1.0``
        Standard deviation for Gaussian kernel.

    n_bins : int, optional, default: ``100``
        The number of filtration parameter values, per available homology
        dimension, to sample during :meth:`fit`.

    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1 unless
        in a :obj:`joblib.parallel_backend` context. ``-1`` means using all
        processors.

    Attributes
    ----------
    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`.

    samplings_ : dict
        For each number in `homology_dimensions_`, a discrete sampling of
        filtration parameters, calculated during :meth:`fit` according to the
        minimum birth and maximum death values observed across all samples.

    See also
    --------
    BettiCurve, PersistenceLandscape, PersistenceEntropy, Amplitude, \
    PairwiseDistance, Silhouette, PersistenceImage, \
    gtda.homology.VietorisRipsPersistence

    Notes
    -----
    The samplings in :attr:`samplings_` are in general different between
    different homology dimensions. This means that the (i, j)-th pixel
    of an image in homology dimension q typically arises from a different
    pair of parameter values to the (i, j)-th pixel of an image in
    dimension q'.

    References
    ----------
    .. [1] J. Reininghaus, S. Huber, U. Bauer, and R. Kwitt, "A Stable
           Multi-Scale Kernel for Topological Machine Learning"; *2015 IEEE
           Conference on Computer Vision and Pattern Recognition (CVPR)*,
           pp. 4741--4748, 2015; doi: `10.1109/CVPR.2015.7299106
           <http://dx.doi.org/10.1109/CVPR.2015.7299106>`_.

    """

    _hyperparameters = {'sigma': [numbers.Number, (1e-16, np.inf)],
                        'n_bins': [int, (1, np.inf)]}

    def __init__(self, sigma=1.0, n_bins=100, n_jobs=None):
        self.sigma = sigma
        self.n_bins = n_bins
        self.n_jobs = n_jobs

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_` and, for each dimension separately,
        store evenly sample filtration parameter values in :attr:`samplings_`.
        Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)
        validate_params(self.get_params(), self._hyperparameters)

        self.homology_dimensions_ = sorted(list(set(X[0, :, 2])))
        self._n_dimensions = len(self.homology_dimensions_)

        self._samplings, self._step_size = _bin(
            X, metric='heat', n_bins=self.n_bins)
        self.samplings_ = {dim: s
                           for dim, s in self._samplings.items()}
        return self

    def transform(self, X, y=None):
        """Compute raster images obtained from diagrams in `X` by convolution
        with a Gaussian kernel.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions, n_bins, \
            n_bins)
            Raster images: one image per sample and per homology dimension seen
            in :meth:`fit`. Index i along axis 1 corresponds to the i-th
            homology dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X, copy=True)

        Xt = Parallel(n_jobs=self.n_jobs)(delayed(
            heats)(_subdiagrams(X, [dim], remove_dim=True)[s],
                   self._samplings[dim], self._step_size[dim], self.sigma)
            for dim in self.homology_dimensions_
            for s in gen_even_slices(X.shape[0],
                                     effective_n_jobs(self.n_jobs)))
        Xt = np.concatenate(Xt).reshape(self._n_dimensions, X.shape[0],
                                        self.n_bins, self.n_bins).\
            transpose((1, 0, 2, 3))
        return Xt


@adapt_fit_transform_docs
class PersistenceImage(BaseEstimator, TransformerMixin):
    """`Persistence images <https://giotto.ai/theory>`_ of persistence
    diagrams.

    Based on ideas in [1]_. Given a persistence diagram consisting of
    birth-death-dimension triples [b, d, q], the equivalent diagrams of
    birth-persistence-dimension [b, d-b, q] triples are computed and
    subdiagrams corresponding to distinct homology dimensions are considered
    separately and regarded as sums of Dirac deltas.
    Then, the convolution with a Gaussian kernel is computed over
    a rectangular grid of locations evenly sampled from appropriate ranges
    of the `filtration parameter <https://giotto.ai/theory>`_.
    The result can be thought of as a raster image.

    Parameters
    ----------
    sigma : float, optional default ``1.0``
        Standard deviation for Gaussian kernel.

    n_bins : int, optional, default: ``100``
        The number of filtration parameter values, per available homology
        dimension, to sample during :meth:`fit`.

    weight_function : fct 1d array -> 1d array, default: ``lambda p: p``
        Function mapping a 1d-array of persistence of the points of a diagram
        to a 1d array of their weight.

    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1 unless
        in a :obj:`joblib.parallel_backend` context. ``-1`` means using all
        processors.

    Attributes
    ----------
    effective_weight_function_ : fct 1d array -> 1d array
        Effective function mapping a 1d-array of persistence of the points of a
        diagram to a 1d array of their weight.

    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`.

    samplings_ : dict
        For each number in `homology_dimensions_`, a discrete sampling of
        filtration parameters, calculated during :meth:`fit` according to the
        minimum birth and maximum death values observed across all samples.

    weights_ : dict
        For each number in `homology_dimensions_`, an array of weights
        corresponding to the persistence values obtained from `samplings_`
        calculated during :meth:`fit` using the `weight_function`.

    See also
    --------
    BettiCurve, PersistenceLandscape, PersistenceEntropy, HeatKernel, \
    Amplitude, PairwiseDistance, gtda.homology.VietorisRipsPersistence

    Notes
    -----
    The samplings in :attr:`samplings_` are in general different between
    different homology dimensions. This means that the (i, j)-th pixel of a
    persistence image in homology dimension q typically arises from a different
    pair of parameter values to the (i, j)-th pixel of a persistence image in
    dimension q'.

    References
    ----------
    .. [1] H. Adams, T. Emerson, M. Kirby, R. Neville, C. Peterson, P. Shipman,
           S. Chepushtanova, E. Hanson, F. Motta, and L. Ziegelmeier,
           "Persistence Images: A Stable Vector Representation of Persistent
           Homology"; *Journal of Machine Learning Research 18, 1*,
           pp. 218-252, 2017; doi: `10.5555/3122009.3122017
           <http://dx.doi.org/10.5555/3122009.3122017>`_.

    """

    _hyperparameters = {'sigma': [numbers.Number, (1e-16, np.inf)],
                        'n_bins': [int, (1, np.inf)],
                        'effective_weight_function_': [types.FunctionType,
                                                       None]}

    def __init__(self, sigma=1.0, n_bins=100, weight_function=None,
                 n_jobs=None):
        self.sigma = sigma
        self.n_bins = n_bins
        self.weight_function = weight_function
        self.n_jobs = n_jobs

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_` and, for each dimension separately,
        store evenly sample filtration parameter values in :attr:`samplings_`.
        Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)

        if self.weight_function is None:
            self.effective_weight_function_ = lambda p: p
        else:
            self.effective_weight_function_ = self.weight_function

        validate_params({
            **self.get_params(),
            'effective_weight_function_': self.effective_weight_function_},
                        self._hyperparameters)

        self.homology_dimensions_ = sorted(list(set(X[0, :, 2])))
        self._n_dimensions = len(self.homology_dimensions_)

        self._samplings, self._step_size = _bin(
            X, metric='persistence_image', n_bins=self.n_bins)
        self.samplings_ = {dim: s
                           for dim, s in self._samplings.items()}
        self.weights_ = _calculate_weights(X, self.effective_weight_function_,
                                           self._samplings)
        return self

    def transform(self, X, y=None):
        """Compute raster images obtained from diagrams in `X` by convolution
        with a Gaussian kernel.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions, n_bins, \
             n_bins)
            Raster images: one image per sample and per homology dimension seen
            in :meth:`fit`. Index i along axis 1 corresponds to the i-th
            homology dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X, copy=True)

        Xt = Parallel(n_jobs=self.n_jobs)(
            delayed(persistence_images)(_subdiagrams(X, [dim],
                                                     remove_dim=True)[s],
                                        self._samplings[dim],
                                        self._step_size[dim],
                                        self.weights_[dim],
                                        self.sigma)
            for dim in self.homology_dimensions_
            for s in gen_even_slices(X.shape[0],
                                     effective_n_jobs(self.n_jobs))
        )
        Xt = np.concatenate(Xt).reshape(self._n_dimensions, X.shape[0],
                                        self.n_bins, self.n_bins).\
            transpose((1, 0, 2, 3))
        return Xt


@adapt_fit_transform_docs
class Silhouette(BaseEstimator, TransformerMixin):
    """`Power-weighted silhouettes <https://giotto.ai/theory>`_ of persistence
    diagrams.

    Based on ideas in [1]_. Given a persistence diagram consisting of
    birth-death-dimension triples [b, d, q], subdiagrams corresponding to
    distinct homology dimensions are considered separately, and their
    respective silhouette by sampling the silhouette function over evenly
    spaced locations from appropriate ranges
    of the `filtration parameter <https://giotto.ai/theory>`_

     Parameters
    ----------
    order: float, optional, default: ``1.``
        The power to which persistence values are raised to define the
        `power-weighted silhouettes <https://giotto.ai/theory>`_.

    n_bins : int, optional, default: ``100``
        The number of filtration parameter values, per available homology
        dimension, to sample during :meth:`fit`.

    n_jobs : int or None, optional, default: ``None``
        The number of jobs to use for the computation. ``None`` means 1
        unless in a :obj:`joblib.parallel_backend` context. ``-1`` means
        using all processors.

    Attributes
    ----------
    homology_dimensions_ : list
        Homology dimensions seen in :meth:`fit`, sorted in ascending order.

    samplings_ : dict
        For each number in `homology_dimensions_`, a discrete sampling of
        filtration parameters, calculated during :meth:`fit` according to the
        minimum birth and maximum death values observed across all samples.

    See also
    --------
    PersistenceLandscape, PersistenceEntropy, HeatKernel, Amplitude, \
    PairwiseDistance, BettiCurve, gtda.homology.VietorisRipsPersistence

    Notes
    -----
    The samplings in :attr:`samplings_` are in general different between
    different homology dimensions. This means that the j-th entry of
    a silhouette in homology dimension q typically arises from
    a different parameter values to the j-th entry of a curve
    in dimension q'.

    References
    ----------
    .. [1] F. Chazal, B. T. Fasy, F. Lecci, A. Rinaldo, and L. Wasserman,
           "Stochastic Convergence of Persistence Landscapes and Silhouettes";
           *In Proceedings of the thirtieth annual symposium on Computational
           Geometry*, Kyoto, Japan, 2014, pp. 474–483;
           doi: `10.1145/2582112.2582128
           <http://dx.doi.org/10.1145/2582112.2582128>`_.

    """

    _hyperparameters = {'order': [float, (0., np.inf)],
                        'n_bins': [int, (1., np.inf)]}

    def __init__(self, order=1., n_bins=100, n_jobs=None):
        self.order = order
        self.n_bins = n_bins
        self.n_jobs = n_jobs

    def fit(self, X, y=None):
        """Store all observed homology dimensions in
        :attr:`homology_dimensions_` and, for each dimension separately,
        store evenly sample filtration parameter values in :attr:`samplings_`.
        Then, return the estimator.

        This method is here to implement the usual scikit-learn API and hence
        work in pipelines.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        self : object

        """
        X = check_diagram(X)
        validate_params(self.get_params(), self._hyperparameters)

        self.homology_dimensions_ = sorted(list(set(X[0, :, 2])))
        self._n_dimensions = len(self.homology_dimensions_)

        self._samplings, _ = _bin(X, metric='silhouette', n_bins=self.n_bins)
        self.samplings_ = {dim: s.flatten()
                           for dim, s in self._samplings.items()}

        return self

    def transform(self, X, y=None):
        """Compute silhouettes of diagrams in X.

        Parameters
        ----------
        X : ndarray of shape (n_samples, n_features, 3)
            Input data. Array of persistence diagrams, each a collection of
            triples [b, d, q] representing persistent topological features
            through their birth (b), death (d) and homology dimension (q).

        y : None
            There is no need for a target in a transformer, yet the pipeline
            API requires this parameter.

        Returns
        -------
        Xt : ndarray of shape (n_samples, n_homology_dimensions, n_bins)
            One silhouette (represented as a one-dimensional array)
            per sample and per homology dimension seen
            in :meth:`fit`. Index i along axis 1 corresponds to the i-th
            homology dimension in :attr:`homology_dimensions_`.

        """
        check_is_fitted(self)
        X = check_diagram(X)

        Xt = (Parallel(n_jobs=self.n_jobs)
              (delayed(silhouettes)(_subdiagrams(X, [dim], remove_dim=True)[s],
                                    self._samplings[dim], order=self.order)
              for dim in self.homology_dimensions_
              for s in gen_even_slices(X.shape[0],
                                       effective_n_jobs(self.n_jobs))))

        Xt = np.concatenate(Xt). \
            reshape(self._n_dimensions, X.shape[0], -1). \
            transpose((1, 0, 2))
        return Xt
