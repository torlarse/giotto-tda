"""Utilities for input validation."""
# License: GNU AGPLv3

import numbers
import types
import numpy as np

available_metrics = {
    'bottleneck': [('delta', numbers.Number, (0., 1.))],
    'wasserstein': [('p', int, (1, np.inf)),
                    ('delta', numbers.Number, (1e-16, 1.))],
    'betti': [('p', numbers.Number, (1, np.inf)),
              ('n_bins', int, (1, np.inf))],
    'landscape': [('p', numbers.Number, (1, np.inf)),
                  ('n_bins', int, (1, np.inf)),
                  ('n_layers', int, (1, np.inf))],
    'heat': [('p', numbers.Number, (1, np.inf)),
             ('n_bins', int, (1, np.inf)),
             ('sigma', numbers.Number, (0., np.inf))],
    'persistence_image': [('p', numbers.Number, (1, np.inf)),
                          ('n_bins', int, (1, np.inf)),
                          ('sigma', numbers.Number, (0., np.inf)),
                          ('weight_function', types.FunctionType,
                           None)]}

available_metric_params = {metric: [p[0] for p in param_lst]
                           for metric, param_lst in available_metrics.items()}


def check_diagram(X, copy=False):
    """Input validation on a diagram
    """
    if len(X.shape) != 3:
        raise ValueError("X should be a 3d np.array: X.shape"
                         " = {}".format(X.shape))
    if X.shape[2] != 3:
        raise ValueError("X should be a 3d np.array with a 3rd dimension of"
                         " 3 components: X.shape[2] = {}".format(X.shape[2]))

    homology_dimensions = sorted(list(set(X[0, :, 2])))
    for dim in homology_dimensions:
        if dim == np.inf:
            if len(homology_dimensions) != 1:
                raise ValueError("np.inf is a valid homology dimension for a "
                                 "stacked diagram but it should be the only "
                                 "one: homology_dimensions "
                                 "= {}".format(homology_dimensions))
        else:
            if dim != int(dim):
                raise ValueError("All homology dimensions should be"
                                 " integer valued: {} can't be casted"
                                 " to an int of the same value.".format(dim))
            if dim != np.abs(dim):
                raise ValueError("All homology dimensions should be"
                                 " integer valued: {} can't be casted"
                                 " to an int of the same value.".format(dim))

    n_points_above_diag = np.sum(X[:, :, 1] >= X[:, :, 0])
    n_points_global = X.shape[0] * X.shape[1]
    if n_points_above_diag != n_points_global:
        raise ValueError("All points of all n_samples persistent diagrams "
                         "should be above the diagonal, X[:,:,1] >= X[:,:,0]."
                         " {} points in "
                         "all n_samples diagrams are under the diagonal."
                         "".format(n_points_global - n_points_above_diag))
    if copy:
        return np.copy(X)
    else:
        return X


def check_graph(X):
    return X


# Check the type and range of numerical parameters
def validate_params(parameters, references):
    for key in references.keys():
        if not isinstance(parameters[key], references[key][0]):
            raise TypeError("Parameter {} is of type {}"
                            " while it should be of type {}"
                            "".format(key, type(parameters[key]),
                                      references[key][0]))
        if len(references[key]) == 1:
            continue
        if references[key][0] == list or \
           references[key][0] == np.ndarray:
            for parameter in parameters[key]:
                if references[key][1][0] == int:
                    if not isinstance(parameter, numbers.Number):
                        raise TypeError("Parameter {} is a {} of {}"
                                        " but contains an element of type {}"
                                        "".format(key, type(parameters[key]),
                                                  references[key][1][0],
                                                  type(parameter)))
                    if not float(parameter).is_integer():
                        raise TypeError("Parameter {} is a {} of int"
                                        " but contains an element of type {}"
                                        " that is not an integer."
                                        "".format(key, type(parameters[key]),
                                                  type(parameter)))
                else:
                    if not isinstance(parameter, references[key][1][0]):
                        raise TypeError("Parameter {} is a {} of {}"
                                        " but contains an element of type {}"
                                        "".format(key, type(parameters[key]),
                                                  references[key][1][0],
                                                  type(parameter)))
                if references[key][1][1] is None:
                    break
                if isinstance(references[key][1][1], tuple):
                    if (parameter < references[key][1][1][0] or
                            parameter > references[key][1][1][1]):
                        raise ValueError("Parameter {} is a list containing {}"
                                         "which should be in the range [{},{}]"
                                         "".format(key, parameter,
                                                   references[key][1][1][0],
                                                   references[key][1][1][1]))
            break
        if references[key][1][1] is None:
            break
            for parameter in parameters[key]:
                if isinstance(references[key][1], tuple):
                    if (parameter < references[key][1][1][0] or
                            parameter > references[key][1][1][1]):
                        raise ValueError(
                            "Parameter {} is an array containing {} which "
                            "should be in the range [{},{}]".format(
                                key, parameter, references[key][1][1][0],
                                references[key][1][1][1]))
            break
        if isinstance(references[key][1], tuple):
            if (parameters[key] < references[key][1][0] or
                    parameters[key] > references[key][1][1]):
                raise ValueError("Parameter {} is {}, while it"
                                 " should be in the range [{}, {}]"
                                 "".format(key, parameters[key],
                                           references[key][1][0],
                                           references[key][1][1]))
        if isinstance(references[key][1], list):
            if parameters[key] not in references[key][1]:
                raise ValueError("Parameter {} is {}, while it"
                                 " should be one of the following {}"
                                 "".format(key, parameters[key],
                                           references[key][1]))


def validate_metric_params(metric, metric_params):
    if metric not in available_metrics.keys():
        raise ValueError("No metric called {}."
                         " Available metrics are {}."
                         "".format(metric,
                                   list(available_metrics.keys())))

    for (param, param_type, param_values) in available_metrics[metric]:
        if param in metric_params.keys():
            input_param = metric_params[param]
            if not isinstance(input_param, param_type):
                raise TypeError("{} in params_metric is of type {}"
                                " but must be an {}."
                                "".format(param, type(input_param),
                                          param_type))
            if param_values is not None:
                if input_param < param_values[0] or \
                   input_param > param_values[1]:
                    raise ValueError("{} in param_metric should be between {} "
                                     "and {} but has been set to {}."
                                     "".format(param, param_values[0],
                                               param_values[1], input_param))

    for param in metric_params.keys():
        if param not in available_metric_params[metric]:
            raise ValueError("{} in metric_param is not an available"
                             " parameter. Available metric_params"
                             " are {}".format(param,
                                              available_metric_params[metric]))
