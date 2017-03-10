import ghalton
import numpy
import sys
# import random
import os

def move_spinner(i):
    '''A function to create a text spinner during long computations'''
    spin = ("|", "/","-", "\\")
    print " [%s] %d\r" % (spin[i%4],i)
    sys.stdout.flush()

class Sample(object):
    ''' An object containing the definition of the sample space, as well as the 
        matrices M_1, M_2, N_j, and N_nj. Generated via Halton low-discrepancy
        sequence by default.
        
        Parameters
        ----------
        k : int
            Number of parameters that the objective function expects
        n : int
            Number of low discrepancy draws to use to estimate the variance
        scaling : function, optional (default: None)
            A function that when passed an array of numbers k long from [0..1]
            scales them to the desired range for the objective function. See
            varsens.scale for helpers.
        discard : int, optional (default: 0)
            Number of samples to discard from the beginning of the generated
            Halton sequence (note that this is in addition to the 20*k that are
            discarded by default). This makes it possible to continue a sample from
            where it was terminated if it is determined that sufficient precision in
            the sensitivity calculations has not been achieved.
        verbose : bool, optional (default: True)
            Verbose output
        raw : Array, optional (default: None)
            A preloaded array, to be used as is with no shuffling. Requires k and n to match.
        loadArgs : keyword arguments, optional
            Arguments for loading pre-generated sample spaces from file (passed to 
            Sample.load()). There are two types of samples that can be loaded: 1) A 
            sample space of dimension (2*n*(1+k),k); this is usually a Halton sample 
            generated in Sample._init_() and exported through Sample.export(); 2) A 
            sample space of dimension (2*n,k); this is usually a sample generated by 
            some other method (e.g., Sobol; see the additional quantlib directory in 
            the varsens package for some C++ quantlib sample space generating code to 
            make a sample file). If a sample space is loaded that does not conform to 
            either of these dimensions then an Exception is raised.
            ---------------------
            Recognized arguments:
            ---------------------
            'loadFile' : Load sample from a single file (required if 'prefix' is not 
                         defined; takes precedence if 'prefix' is defined).
            'prefix'   : Sample file prefix (required if 'loadFile' is not defined).
                         Can be either a simple string or a file path.
            'indir'    : Input directory (required if 'prefix' is not a path).
            'nFiles'   : Number of files to read sample from (required if 'prefix' 
                         is defined).
            'offset'   : Starting index for input filenames (optional; default=1).
            'postfix'  : File postfix (optional; default = '.txt').
            'delimiter': Column delimiter in input files (optional; default = '\t').
    '''
    def __init__(self, k, n, scaling=None, discard=0, verbose=True, raw=None, **loadArgs):
        
        self.k = int(k) # Cast to int to allow for scientific notation (useful for large models).
        self.n = int(n)
        self.scaling = scaling
        self.verbose = verbose

        if not raw is None:
            if self.verbose: print "Using provided raw sample"
            x = raw
            if x.shape != (2*self.n, self.k):
              raise Exception("Raw sample dimensions do not match specified dimensions")           
        elif loadArgs:
            if self.verbose: print "Loading Sample from loadArgs"
            x = self.load(**loadArgs)
            if x.shape == (2*self.n*(1+self.k), self.k): return
        else: # Generate the sample
            if self.verbose: print "Generating Low Discrepancy Sequence"
            if not self.scaling:
                raise Exception("Generating a fresh sample space requires that a 'scaling' function be defined.")
            seq = ghalton.Halton(self.k)
            seq.get(20*self.k + int(discard)) # Remove initial linear correlated points plus any additional specified by the user.
            x = numpy.array(seq.get(2*self.n))

        if scaling is None:
            if self.verbose: print "Defaulting to identity scaling of parameter space"
            self.scaling = lambda x:x

        
        if self.verbose: print "Generating M_1"
        self.M_1 = self.scaling(x[0:self.n,...])
        
        if self.verbose: print "Generating M_2"
        self.M_2 = self.scaling(x[self.n:(2*self.n),...])

        # NOTE: This is the magic trick that makes it all work, not mentioned in Saltelli's papers.
        # There can be no correlation between sample M_1 and M_2
        if not raw is None:
            if self.verbose: print "Eliminating correlations"
            numpy.random.seed(1)
            numpy.random.shuffle(self.M_2) # Eliminate any correlation

        # Generate the sample/resample permutations
        if self.verbose: print "Generating N_j"
        self.N_j  = self.generate_N_j(self.M_1, self.M_2) # See Eq (11)
        
        if self.verbose: print "Generating N_nj"
        self.N_nj = self.generate_N_j(self.M_2, self.M_1)
        
        if self.verbose: print "...Sample Created."
    
    def generate_N_j(self, M_1, M_2):
        '''When passing the quasi-random low discrepancy-treated M_1 and M_2 matrices, 
        this function iterates over all the possibilities and returns the N_j matrix for 
        simulations. See e.g. Saltelli, Ratto, Andres, Campolongo, Cariboni, Gatelli, 
        Saisana, Tarantola, "Global Sensitivity Analysis"'''

        # allocate the space for the C matrix
        N_j = numpy.array([M_2]*self.k)

        # Now we have nparams copies of M_2. replace the i_th column of N_j with the i_th column of M_1
        for i in range(self.k):
            N_j[i,:,i] = M_1[:,i]
            
        return N_j

    def flat(self):
        '''Return the sample space as an array 2*n*(1+k) long, containing arrays k long'''
        
        # NEW CODE: Pre-allocates the flat matrix and then fills it
        # ----------------------------------------------------------
        if self.verbose: print "Flattening sample space..."
        
        l1 = len(self.M_1)
        l2 = len(self.M_2)
        l3 = self.N_j.shape[0]*self.N_j.shape[1]
        l4 = self.N_nj.shape[0]*self.N_nj.shape[1]
          
        x = numpy.zeros((l1+l2+l3+l4,self.k))
        
        if self.verbose: print "Flattening M_1"
        x[0:l1]  = self.M_1
        
        if self.verbose: print "Flattening M_2"
        x[l1:l1+l2] = self.M_2
        
        if self.verbose: print "Flattening N_j"
        curr_length = l1+l2
        for i in range(self.k):
            x[curr_length:curr_length+len(self.N_j[i])] = self.N_j[i]
            curr_length += len(self.N_j[i])
        
        if self.verbose: print "Flattening N_nj"
        for i in range(self.k):
            x[curr_length:curr_length+len(self.N_nj[i])] = self.N_nj[i]
            curr_length += len(self.N_nj[i])
        
        if self.verbose: print "...Done. ( flattened.shape = ", x.shape, ")"
        
        return x
        
        # OLD CODE: Uses expensive .append() calls
        # -----------------------------------------
#         x = numpy.append(self.M_1, self.M_2, axis=0)
#         for i in range(self.k): 
#             print i
#             x = numpy.append(x, self.N_j[i], axis=0)
#         for i in range(self.k): 
#             print i
#             x = numpy.append(x, self.N_nj[i], axis=0)
#         return x

    def export(self, outdir=os.getcwd(), prefix="sample", postfix=".txt", blocksize=float("inf"), delimiter="\t"):
        # Flatten
        f = self.flat()
        # Sanity checks
        if blocksize > len(f): blocksize = len(f)
        else: blocksize = int(blocksize) # just to be safe
        prefix = str(prefix) # just to be safe
        prefix="_".join(prefix.split()) # remove all whitespace and join with underscores (just in case)
        if prefix[-1] == "_": prefix = prefix[:-1] # remove underscore at the end if there is one
        prefix = os.path.join(outdir,prefix)
        # Write to file
        nFiles = int(numpy.ceil(float(len(f)) / blocksize))
        if nFiles == 1:
            if self.verbose: print "Writing to %s%s ..." % (prefix, postfix),
            numpy.savetxt("%s%s" % (prefix, postfix), f, delimiter=delimiter)
            if self.verbose: print "Done."
        else:
            for b in range(nFiles):
                if self.verbose: print "Writing to %s_%d%s ..." % (prefix, b+1, postfix),
                numpy.savetxt("%s_%d%s" % (prefix, b+1, postfix), f[b*blocksize : (b+1)*blocksize], delimiter=delimiter)
                if self.verbose: print "Done."
                
    def load(self, indir='', loadFile=None, prefix=None, postfix='.txt', nFiles=None, offset=1, delimiter='\t'):
        
        FILES = []
        if loadFile:
            FILES.append(os.path.join(indir,loadFile))
        else:
            # If 'loadFile' not defined then 'prefix' needs to be
            if not prefix: 
                raise Exception("Either 'loadFile' or 'prefix' are required to load a sample from file.")
            # If 'prefix' defined then 'nFiles' needs to be
            if not nFiles: 
                raise Exception("Loading sample files with 'prefix' requires defining 'nFiles'.")
    
            if prefix[-1] != "_": prefix += "_" 
            for i in range(offset,offset+nFiles):
                FILES.append(os.path.join(indir,prefix)+str(i)+postfix)
                
        sample = []
        for file in FILES:
            if not os.path.isfile(file):
                raise Exception("Cannot find input file "+file)
            if self.verbose: print "Reading "+file+" ...",
            sample.append(numpy.loadtxt(open(file, "rb"), delimiter=delimiter))
            if self.verbose: print "Done."
        
        if self.verbose: print "Stacking...",
        x = numpy.vstack(sample)
        if self.verbose: print "Done."
                    
        # Pre-generated UNSCALED sample
        if x.shape == (2*self.n, self.k):
            if not self.scaling:
                raise Exception("Loading a pre-generated, unscaled sample space requires that a 'scaling' function be defined.")
        # Flattened SCALED sample
        elif x.shape == (2*self.n*(1+self.k), self.k): 
            if self.verbose: print "Flattened sample detected"
            if self.verbose: print "Extracting M_1"
            self.M_1 = x[0:self.n,...]
            if self.verbose: print "Extracting M_2"
            self.M_2 = x[self.n:2*self.n,...]
            if self.verbose: print "Extracting N_j"
            curr_length = 2*self.n
            self.N_j = numpy.zeros((self.k, self.n, self.k))
            for i in range(self.k):
                self.N_j[i] = x[curr_length:curr_length+self.n,...]
                curr_length += self.n
            if self.verbose: print "Extracting N_nj"
            self.N_nj = numpy.zeros((self.k, self.n, self.k))
            for i in range(self.k):
                self.N_nj[i] = x[curr_length:curr_length+self.n,...]
                curr_length += self.n
            if self.verbose: print "...Done."
        else:
            raise Exception("Loaded sample has shape "+str(x.shape)+". Must have shape (%d,%d) or (%d,%d)." % (2*self.n, self.k, 2*self.n*(1+self.k), self.k))
        
        return x
    
class Objective(object):
    ''' Function parmeval calculates the fM_1, fM_2, and fN_ji arrays needed for variance-based
    global sensitivity analysis as prescribed by Saltelli and derived from the work by Sobol
    (low-discrepancy sequences)
    
    Parameters
    ----------
    k : int
        Number of parameters that the objective function expects.
    n : int
        Number of low discrepancy draws to use to estimate the variance.
    sample : Sample, optional (default: None)
        The sample object containing the sample space for the computation.
    objective_func : function, optional (default: None)
        Will be passed each point in the sample space and must return a value, or vector of values
        for multi-objective computation.
    verbose : bool, optional (default: True)
        Verbose output.
    loadArgs : keyword arguments, optional
            Arguments for loading pre-calculated objective values from file (passed to 
            Objective.load()). If the dimension of the loaded array is not (2*n*(1+k),k)
            then an Exception is raised.
            ---------------------
            Recognized arguments:
            ---------------------
            'loadFile' : Load objective from a single file (required if 'prefix' is not defined; 
                         takes precedence if 'prefix' is defined).
            'prefix'   : Objective file prefix (required if 'loadFile' is not defined).
                         Can be either a simple string or a file path.
            'indir'    : Input directory (required if 'prefix' is not a path).
            'nFiles'   : Number of files to read objective from (required if 'prefix' is defined).
            'offset'   : Starting index for input filenames (optional; default=1).
            'postfix'  : File postfix (optional; default = '.txt').
    '''
    def __init__(self, k, n, sample=None, objective_func=None, objective_vals=[], verbose=True, **loadArgs):

        self.k              = k
        self.n              = n
        self.sample         = sample
        self.objective_func = objective_func
        self.verbose        = verbose

        if self.verbose: print "Generating Objective Values..."
        
        if len(objective_vals) > 0: # values loaded in an array
            self.load(objective_vals)
        elif loadArgs: # load values from file
            self.load(**loadArgs)
        else: # generate the objective
            if not self.sample:
                raise Exception("Generating a fresh objective requires that a 'sample' be defined.")
            elif not self.objective_func:
                raise Exception("Generating a fresh objective requires that an 'objective_func' be defined.")

            # Determine objective_func return type
            test = self.objective_func(sample.M_1[0])
            
            # assign the arrays that will hold fM_1, fM_2, fN_j, and fN_nj
            try:
                l = len(test)
                self.fM_1  = numpy.zeros((self.n, l))
                self.fM_2  = numpy.zeros((self.n, l))
                self.fN_j  = numpy.zeros((self.k, self.n, l))
                self.fN_nj = numpy.zeros((self.k, self.n, l))
            except TypeError:
                self.fM_1  = numpy.zeros((self.n, 1))
                self.fM_2  = numpy.zeros((self.n, 1))
                self.fN_j  = numpy.zeros((self.k, self.n, 1))
                self.fN_nj = numpy.zeros((self.k, self.n, 1))
            
            step = 0
            total = 2*self.n*(1+self.k)
            output = 0.01*total
            output = int(output) if output > 1 else 1
            
            if self.verbose: print "Processing f(M_1):"
            self.fM_1[0] = test # Save first execution
            for i in range(1,self.n):
                self.fM_1[i] = self.objective_func(sample.M_1[i])
                step += 1
                if self.verbose and step % output == 0: print str(int(round(100.*step/total)))+"%" #move_spinner(i)
                
            if self.verbose: print "Processing f(M_2):"
            for i in range(self.n):
                self.fM_2[i] = self.objective_func(sample.M_2[i])
                step += 1
                if self.verbose and step % output == 0: print str(int(round(100.*step/total)))+"%" #move_spinner(i)
        
            if self.verbose: print "Processing f(N_j)"
            for i in range(self.k):
                if self.verbose: print " * parameter %d"%i
                for j in range(self.n):
                    self.fN_j[i][j] = self.objective_func(sample.N_j[i][j])
                    step += 1 
                    if self.verbose and step % output == 0: print str(int(round(100.*step/total)))+"%" #move_spinner(i)
        
            if self.verbose: print "Processing f(N_nj)"
            for i in range(self.k):
                if self.verbose: print " * parameter %d"%i
                for j in range(self.n):
                    self.fN_nj[i][j] = self.objective_func(sample.N_nj[i][j])
                    step += 1
                    if self.verbose and step % output == 0: print str(int(round(100.*step/total)))+"%" #move_spinner(i)

    def flat(self):
        '''Return the objectives as an array 2*n*(1+k) long'''

        if self.verbose: print "Flattening objectives..."
        
        l1 = len(self.fM_1)
        l2 = len(self.fM_2)
        l3 = self.fN_j.shape[0]*self.fN_j.shape[1]
        l4 = self.fN_nj.shape[0]*self.fN_nj.shape[1]
                
        if len(self.fM_1.shape) > 1:
            x = numpy.zeros(((l1+l2+l3+l4), self.fM_1.shape[1]))
        else:
            x = numpy.zeros(l1+l2+l3+l4)
        
        if self.verbose: print "Flattening fM_1"
        x[0:l1,...]  = self.fM_1
        
        if self.verbose: print "Flattening fM_2"
        x[l1:l1+l2,...] = self.fM_2
        
        if self.verbose: print "Flattening fN_j"
        curr_length = l1+l2
        for i in range(self.k):
            x[curr_length:curr_length+len(self.fN_j[i]),...] = self.fN_j[i]
            curr_length += len(self.fN_j[i])
        
        if self.verbose: print "Flattening fN_nj"
        for i in range(self.k):
            x[curr_length:curr_length+len(self.fN_nj[i]),...] = self.fN_nj[i]
            curr_length += len(self.fN_nj[i])
        
        if self.verbose: print "...Done. ( flattened.shape = ", x.shape, ")"
        
        return x

    def export(self, outdir=os.getcwd(), prefix="objective", postfix=".txt", blocksize=float("inf")):
        # Flatten
        f = self.flat()
        # Sanity checks
        if blocksize > len(f): blocksize = len(f)
        else: blocksize = int(blocksize) # just to be safe
        prefix = str(prefix) # just to be safe
        prefix="_".join(prefix.split()) # remove all whitespace and join with underscores (just in case)
        if prefix[-1] == "_": prefix = prefix[:-1] # remove underscore at the end if there is one
        prefix = os.path.join(outdir,prefix)
        # Write to file
        nFiles = int(numpy.ceil(float(len(f)) / blocksize))
        if nFiles == 1:
            if self.verbose: print "Writing to %s%s ..." % (prefix, postfix),
            numpy.savetxt("%s%s" % (prefix, postfix), f)
            if self.verbose: print "Done."
        else:
            for b in range(nFiles):
                if self.verbose: print "Writing to %s_%d%s ..." % (prefix, b+1, postfix),
                numpy.savetxt("%s_%d%s" % (prefix, b+1, postfix), f[b*blocksize : (b+1)*blocksize])
                if self.verbose: print "Done."

    def load(self, obj_vals=[], indir='', loadFile=None, prefix=None, postfix='.txt', nFiles=None, offset=1, scaling=1.0):
        
        if len(obj_vals) > 0:
            x = obj_vals
        else:
            FILES = []
            if loadFile:
                FILES.append(os.path.join(indir,loadFile))
            else:
                # If 'loadFile' not defined then 'prefix' needs to be
                if not prefix: 
                    raise Exception("Either 'loadFile' or 'prefix' are required to load an objective from file.")
                # If 'prefix' defined then 'nFiles' needs to be
                if not nFiles: 
                    raise Exception("Loading objective files with 'prefix' requires defining 'nFiles'.")
                if prefix[-1] != "_": prefix += "_" 
                for i in range(offset,offset+nFiles):
                    FILES.append(os.path.join(indir,prefix)+str(i)+postfix)
                    
            obj = []
            for file in FILES:
                if not os.path.isfile(file):
                    raise Exception("Cannot find input file "+file)
                if self.verbose: print "Reading "+file+" ...",
                obj.append(numpy.loadtxt(open(file, "rb")))
                if self.verbose: print "Done."
            
            if self.verbose: print "Stacking...",
            if len(numpy.array(obj).shape) == 2: # one observable (list of 1-D arrays)
                x = numpy.hstack(obj)
            else: # more than one observable
                x = numpy.vstack(obj)
            if self.verbose: print "Done."
        
        if len(x) == 2*self.n*(1+self.k): 
            if self.verbose: print "Extracting fM_1"
            self.fM_1 = x[0:self.n,...] / scaling
            if self.verbose: print "Extracting fM_2"
            self.fM_2 = x[self.n:2*self.n,...] / scaling
            curr_length = 2*self.n
            try: 
                l = len(x[0])
                self.fN_j = numpy.zeros((self.k, self.n, l))
                self.fN_nj = numpy.zeros((self.k, self.n, l))
            except TypeError:
                self.fN_j = numpy.zeros((self.k, self.n, 1))
                self.fN_nj = numpy.zeros((self.k, self.n, 1))
            if self.verbose: print "Extracting fN_j"
            for i in range(self.k):
                self.fN_j[i] = x[curr_length:curr_length+self.n,...] / scaling
                curr_length += self.n
            if self.verbose: print "Extracting fN_nj"
            for i in range(self.k):
                self.fN_nj[i] = x[curr_length:curr_length+self.n,...] / scaling
                curr_length += self.n
            if self.verbose: print "...Done."
        else:
            raise Exception("Loaded objective has length "+str(len(x))+". Must have length %d." % (2*self.n*(1+self.k)))
        
        # Trim the row from *all* matrices if *one* has a nan
        nans = [] 
        # locate nans
        isnan = numpy.logical_or(numpy.isnan(self.fM_1), numpy.isnan(self.fM_2))
        for i in range(self.k):
            isnan = numpy.logical_or(isnan, numpy.isnan(self.fN_j[i]))
            isnan = numpy.logical_or(isnan, numpy.isnan(self.fN_nj[i]))
        # If there are multiple objectives, use the first column
        if len(isnan.shape) > 1: isnan = isnan[:,0]

        # Construct array of NaN rows
        for i in range(len(isnan)):
            if isnan[i]: nans.append(i)
        
        # Now delete the located nans
        self.fM_1     = numpy.delete(self.fM_1,  nans, axis=0)
        self.fM_2     = numpy.delete(self.fM_2,  nans, axis=0)
        self.fN_j     = numpy.delete(self.fN_j,  nans, axis=1)
        self.fN_nj    = numpy.delete(self.fN_nj, nans, axis=1)
        
        if len(nans) > 0:
            print "WARNING: %d of %d objectives were NaN, %lf%% loss\r" % (len(nans), 2*self.n*(1+self.k), 100.0*len(nans)/(2*self.n*(1+self.k)))

class Varsens(object):
    '''The main variance sensitivity object which contains the core of the computation. It will
        execute the objective function 2*n*(k+1) times.
        
        Parameters
        ----------
        objective : function or Objective
            a function that is passed k parameters resulting in a value or 
            list of values to evaluate it's sensitivity, or a pre-evaluated set
            of objectives in an Objective object
        scaling_func : function
            A function that when passed an array of numbers k long from [0..1]
            scales them to the desired range for the objective function. See
            varsens.scale for helpers.
        k : int
            Number of parameters that the objective function expects
        n : int
            Number of low discrepancy draws to use to estimate the variance
        sample : Sample
            A predefined sample. If specified, the k, n and scaling_func variables
            are ignored, and this is used as the sample
        verbose : bool
            Whether or not to print progress in computation

        Returns
        -------
        Varsens object. It will contain var_y, E_2, sens and sens_t.

        Examples
        ________
            >>> from varsens    import *
            >>> import numpy
            >>> def gi_function(xi, ai): return (numpy.abs(4.0*xi-2.0)+ai) / (1.0+ai)
            ... 
            >>> def g_function(x, a): return numpy.prod([gi_function(xi, a[i]) for i,xi in enumerate(x)])
            ... 
            >>> def g_scaling(x): return x
            ... 
            >>> def g_objective(x): return g_function(x, [0, 0.5, 3, 9, 99, 99])
            ... 
            >>> v = Varsens(g_objective, g_scaling, 6, 1024, verbose=False)
            >>> v.var_y # doctest: +ELLIPSIS
            0.5...
            >>> v.sens # doctest: +ELLIPSIS
            array([...])
            >>> v.sens_t # doctest: +ELLIPSIS
            array([...])
    '''
    def __init__(self, objective, scaling_func=None, k=None, n=None, sample=None, verbose=True):
        self.verbose = verbose
        # If the sample object is predefined use it
        if isinstance(sample, Sample):
            self.sample = sample
            self.k      = sample.k
            self.n      = sample.n
        elif k != None and n != None and scaling_func != None: # Create sample from space definition
            self.k      = k
            self.n      = n
            self.sample = Sample(k, n, scaling_func, verbose)
        elif not isinstance(objective, Objective):
            # No sample provided, no sample space definition provided, no pre-evaluated Objective provided
            # Impossible to compute variable sensitivity
            raise ValueError("Must specify sample, (k,n,scaling_func), or Objective object")

        # Execute the model to determine the objective function
        if isinstance(objective, Objective):
            self.objective = objective
            self.k         = objective.k
            self.n         = objective.n
        else: # The object is predefined.
            self.objective = Objective(self.k, self.n, self.sample, objective, verbose)

        # From the model executions, compute the variable sensitivity
        self.compute_varsens()

    def compute_varsens(self):
        ''' Main computation of sensitivity via Saltelli method.'''
        if self.verbose: print "Final sensitivity calculation"
        
#         n = len(self.objective.fM_1)
        self.E_2 = sum(self.objective.fM_1*self.objective.fM_2) / self.n      # Eq (21)
#         self.E_2 = sum(self.objective.fM_1) / self.n # Eq(22)
#         self.E_2 *= self.E_2
        
        #estimate V(y) from self.objective.fM_1 and self.objective.fM_2
        # paper uses only self.objective.fM_1, this is a better estimator
        self.var_y = numpy.var(numpy.concatenate((self.objective.fM_1, self.objective.fM_2), axis=0), axis=0, ddof=1)

# FIXME: This NEED WORK, and it is IMPORTANT
        #if not numpy.all(numpy.sqrt(numpy.abs(self.E_2)) > 1.96*numpy.sqrt(self.var_y / self.n)):
        #    print "Excessive variance in estimation of E^2"
        #    raise ArithmeticError
        
        # Estimate U_j and U_-j values and store them, but by double method
        self.U_j  =  numpy.sum(self.objective.fM_1 * self.objective.fN_j,  axis=1) / (self.n - 1)  # Eq (12)
        self.U_j  += numpy.sum(self.objective.fM_2 * self.objective.fN_nj, axis=1) / (self.n - 1) 
        self.U_j  /= 2.0
        self.U_nj =  numpy.sum(self.objective.fM_1 * self.objective.fN_nj, axis=1) / (self.n - 1)  # Eq (unnumbered one after 18)
        self.U_nj += numpy.sum(self.objective.fM_2 * self.objective.fN_j,  axis=1) / (self.n - 1) 
        self.U_nj /= 2.0
        
        #allocate the S_i and ST_i arrays
        if len(self.U_j.shape) == 1:
            self.sens   = numpy.zeros(self.k)
            self.sens_t = numpy.zeros(self.k)
        else: # It's a list of values
            self.sens   = numpy.zeros([self.k]+[self.U_j.shape[1]])
            self.sens_t = numpy.zeros([self.k]+[self.U_j.shape[1]])
        
        # now get the S_i and ST_i, Eq (27) & Eq (28)
        for j in range(self.k):
            self.sens[j]   = (self.U_j[j] - self.E_2) / self.var_y
            self.sens_t[j] = 1.0 - ((self.U_nj[j]- self.E_2) / self.var_y)
            
        # Compute 2nd order terms (from double estimates)
        self.sens_2  =  numpy.tensordot(self.objective.fN_nj, self.objective.fN_j,  axes=([1],[1]))
        self.sens_2  += numpy.tensordot(self.objective.fN_j,  self.objective.fN_nj, axes=([1],[1]))
        self.sens_2  /= 2.0 * (self.n-1)
        self.sens_2  -= self.E_2
        self.sens_2  /= self.var_y
        
        self.sens_2n =  numpy.tensordot(self.objective.fN_nj, self.objective.fN_nj, axes=([1],[1]))
        self.sens_2n += numpy.tensordot(self.objective.fN_j,  self.objective.fN_j,  axes=([1],[1]))
        self.sens_2n /= 2.0 * (self.n-1)
        self.sens_2n -= self.E_2
        self.sens_2n /= self.var_y

        # Numerical error can make some values exceed what is sensible
#         self.sens    = numpy.clip(self.sens,    0, 1)
#         self.sens_t  = numpy.clip(self.sens_t,  0, 1e6)
#         self.sens_2  = numpy.clip(self.sens_2,  0, 1)
#         self.sens_2n = numpy.clip(self.sens_2n, 0, 1)
