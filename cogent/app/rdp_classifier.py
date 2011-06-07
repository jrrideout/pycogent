#!/usr/bin/env python
"""Application controller for rdp_classifier-2.0
"""

__author__ = "Kyle Bittinger"
__copyright__ = "Copyright 2007-2011, The Cogent Project"
__credits__ = ["Kyle Bittinger","Greg Caporaso"]
__license__ = "GPL"
__version__ = "1.6.0dev"
__maintainer__ = "Kyle Bittinger"
__email__ = "kylebittinger@gmail.com"
__status__ = "Prototype"


import os.path
import re
from os import remove, environ, getenv, path
from optparse import OptionParser
from shutil import rmtree
import tempfile
from cogent.app.parameters import Parameter, ValuedParameter, Parameters
from cogent.parse.fasta import MinimalFastaParser
from cogent.app.util import CommandLineApplication, CommandLineAppResult, \
    FilePath, ResultPath, guess_input_handler, system,\
    ApplicationNotFoundError, ApplicationError
from cogent.util.misc import app_path

class RdpClassifier(CommandLineApplication):
    """RDP Classifier application controller

    The RDP Classifier program is distributed as a java archive (.jar)
    file.  If the file 'rdp_classifier-2.2.jar' is not found in the
    current directory, the app controller uses the JAR file specified
    by the environment variable RDP_JAR_PATH.  If this variable is not
    set, and 'rdp_classifier-2.2.jar' is not found in the current
    directory, the application controller raises an
    ApplicationNotFoundError.

    The RDP Classifier often requires memory in excess of Java's
    default 64M. To correct this situation, the authors recommend
    increasing the maximum heap size for the java virtual machine.  An
    option '-Xmx' (default 1000M) is provided for this purpose.
    Details on this option may be found at
    http://java.sun.com/j2se/1.5.0/docs/tooldocs/solaris/java.html

    The classifier may optionally use a custom training set.  The full
    path to the training set may be provided in the option
    '-training-data'.
    """
    _input_handler = '_input_as_lines'
    _command = "rdp_classifier-2.2.jar"
    _options = {
        # output file name for classification assignment
        '-o': ValuedParameter('-', Name='o', Delimiter=' ', IsPath=True),
        # a property file contains the mapping of the training
        # files. Note: the training files and the property file should
        # be in the same directory. The default property file is set
        # to data/classifier/rRNAClassifier.properties.
        '-t': ValuedParameter('-', Name='t', Delimiter=' ', IsPath=True),
        # all tab delimited output format: [allrank|fixrank|db].
        # Default is allrank.
        #
        #   allrank: outputs the results for all ranks applied for
        #   each sequence: seqname, orientation, taxon name, rank,
        #   conf, ...
        #
        #   fixrank: only outputs the results for fixed ranks in
        #   order: no rank, domain, phylum, class, order, family,
        #   genus
        #
        #   db: outputs the seqname, trainset_no, tax_id, conf. This
        #   is good for storing in a database
        '-f': ValuedParameter('-', Name='f', Delimiter=' '),
        }

    # The following are available in the attributes JvmParameters,
    # JarParameters, and PositionalParameters

    _jvm_synonyms = {}
    _jvm_parameters = {
        # Maximum heap size for JVM.
        '-Xmx': ValuedParameter('-', Name='Xmx', Delimiter='', Value='1000m'),
        }

    _parameters = {}
    _parameters.update(_options)
    _parameters.update(_jvm_parameters)

    def getHelp(self):
        """Returns documentation string"""
        # Summary paragraph copied from rdp_classifier-2.0, which is
        # licensed under the GPL 2.0 and Copyright 2008 Michigan State
        # University Board of Trustees
        help_str = """\
        usage: ClassifierCmd [-f <arg>] [-o <arg>] [-q <arg>] [-t <arg>]

        -f,--format <arg> all tab delimited output format:
        [allrank|fixrank|db]. Default is allrank.

            allrank: outputs the results for all ranks applied for each
            sequence: seqname, orientation, taxon name, rank, conf, ...

            fixrank: only outputs the results for fixed ranks in order:
            no rank, domain, phylum, class, order, family, genus

            db: outputs the seqname, trainset_no, tax_id, conf. This is
            good for storing in a database

        -o,--outputFile <arg> output file name for classification
        assignment

        -q,--queryFile <arg> query file contains sequences in one of
        the following formats: Fasta, Genbank and EMBL

        -t,--train_propfile <arg> a property file contains the mapping
        of the training files.
        
        Note: the training files and the property file should be in
        the same directory. The default property file is set to
        data/classifier/rRNAClassifier.properties."""
        return help_str

    def _accept_exit_status(self, status):
        """Returns false if an error occurred in execution
        """
        return (status == 0)

    def _error_on_missing_application(self,params):
        """Raise an ApplicationNotFoundError if the app is not accessible

        In this case, checks for the java runtime and the RDP jar file.
        """
        if not (os.path.exists('java') or app_path('java')):
            raise ApplicationNotFoundError(
                "Cannot find java runtime. Is it installed? Is it in your "
                "path?")
        jar_fp = self._get_jar_fp()
        if jar_fp is None:
            raise ApplicationNotFoundError(
                "JAR file not found in current directory and the RDP_JAR_PATH "
                "environment variable is not set.  Please set RDP_JAR_PATH to "
                "the full pathname of the JAR file.")
        if not os.path.exists(jar_fp):
            raise ApplicationNotFoundError(
                "JAR file %s does not exist." % jar_fp)

    def _get_jar_fp(self):
        """Returns the full path to the JAR file.

        If the JAR file cannot be found in the current directory and
        the environment variable RDP_JAR_PATH is not set, returns
        None.
        """
        # handles case where the jar file is in the current working directory
        if os.path.exists(self._command):
            return self._command
        # handles the case where the user has specified the location via
        # an environment variable
        elif 'RDP_JAR_PATH' in environ:
            return getenv('RDP_JAR_PATH')
        else:
            return None

    # Overridden to pull out JVM-specific command-line arguments.
    def _get_base_command(self):
        """Returns the base command plus command-line options.

        Does not include input file, output file, and training set.
        """
        cd_command = ''.join(['cd ', str(self.WorkingDir), ';'])
        jvm_command = "java"
        jvm_arguments = self._commandline_join(
            [self.Parameters[k] for k in self._jvm_parameters])
        jar_arguments = '-jar "%s"' % self._get_jar_fp()
        rdp_arguments = self._commandline_join(
            [self.Parameters[k] for k in self._options])

        command_parts = [
            cd_command, jvm_command, jvm_arguments, jar_arguments,
            rdp_arguments, '-q']
        return self._commandline_join(command_parts).strip()
    
    BaseCommand = property(_get_base_command)

    def _commandline_join(self, tokens):
        """Formats a list of tokens as a shell command
 
        This seems to be a repeated pattern; may be useful in
        superclass.
        """
        commands = filter(None, map(str, tokens))
        return self._command_delimiter.join(commands).strip()

    def _get_result_paths(self,data):
        """ Return a dict of ResultPath objects representing all possible output
        """
        assignment_fp = str(self.Parameters['-o'].Value).strip('"')
        if not os.path.isabs(assignment_fp):
            assignment_fp = os.path.relpath(assignment_fp, self.WorkingDir)
        return {'Assignments': ResultPath(assignment_fp, IsWritten=True)}


class RdpClassifier20(RdpClassifier):
    """RDP Classifier version 2.0 application controller

    The RDP Classifier program is distributed as a java archive (.jar)
    file.  If the file 'rdp_classifier-2.0.jar' is not found in the
    current directory, the app controller looks in the directory
    specified by the environment variable RDP_JAR_PATH.  If this
    variable is not set, and 'rdp_classifier-2.0.jar' is not found in
    the current directory, the application controller raises an
    ApplicationNotFoundError.

    The RDP Classifier often requires memory in excess of Java's
    default 64M. To correct this situation, the authors recommend
    increasing the maximum heap size for the java virtual machine.  An
    option '-Xmx' (default 1000M) is provided for this purpose.
    Details on this option may be found at
    http://java.sun.com/j2se/1.5.0/docs/tooldocs/solaris/java.html

    The classifier may optionally use a custom training set.  The full
    path to the training set may be provided in the option
    '-training-data'.
    """
    _input_handler = '_input_as_multiline_string'
    _command = "rdp_classifier-2.0.jar"
    _options ={}

    # The following are available in the attributes JvmParameters,
    # JarParameters, and PositionalParameters

    _jvm_synonyms = {}
    _jvm_parameters = {
        # Maximum heap size for JVM.
        '-Xmx': ValuedParameter('-', Name='Xmx', Delimiter='', Value='1000m'),
        }
    _positional_synonyms = {}
    _positional_parameters = {
        '-training-data': ValuedParameter('', Name='', Delimiter='', Value='', IsPath=True),
        }

    _parameters = {}
    _parameters.update(_options)
    _parameters.update(_jvm_parameters)
    _parameters.update(_positional_parameters)

    def getHelp(self):
        """Returns documentation string"""
        # Summary paragraph copied from rdp_classifier-2.0, which is
        # licensed under the GPL 2.0 and Copyright 2008 Michigan State
        # University Board of Trustees
        help_str =\
        """
        Ribosomal Database Project - Classifier
        http://rdp.cme.msu.edu/classifier/

        The RDP Classifier is a naive Bayesian classifier which was
        developed to provide rapid taxonomic placement based on rRNA
        sequence data. The RDP Classifier can rapidly and accurately
        classify bacterial 16s rRNA sequences into the new
        higher-order taxonomy proposed by Bergey's Trust. It provides
        taxonomic assignments from domain to genus, with confidence
        estimates for each assignment. The RDP Classifier is not
        limited to using the bacterial taxonomy proposed by the
        Bergey's editors. It worked equally well when trained on the
        NCBI taxonomy. The RDP Classifier likely can be adapted to
        additional phylogenetically coherent bacterial taxonomies.

        The following paper should be cited if this resource is used:

        Wang, Q, G. M. Garrity, J. M. Tiedje, and J. R. Cole. 2007.
        Naive Bayesian Classifier for Rapid Assignment of rRNA
        Sequences into the New Bacterial Taxonomy.  Appl Environ
        Microbiol. 73(16):5261-7.
        """
        return help_str

    def __call__(self, data=None, remove_tmp=True):
        """Run the application with the specified kwargs on data
        
            data: anything that can be cast into a string or written out to
                a file. Usually either a list of things or a single string or 
                number. input_handler will be called on this data before it 
                is passed as part of the command-line argument, so by creating
                your own input handlers you can customize what kind of data
                you want your application to accept

            remove_tmp: if True, removes tmp files
        """
        input_handler = self.InputHandler
        suppress_stdout = self.SuppressStdout
        suppress_stderr = self.SuppressStderr
        assignment_fp = FilePath(self.getTmpFilename(self.TmpDir))
        if suppress_stdout:
            outfile = FilePath('/dev/null')
        else:
            outfile = FilePath(self.getTmpFilename(self.TmpDir))
        if suppress_stderr:
            errfile = FilePath('/dev/null')
        else:
            errfile = FilePath(self.getTmpFilename(self.TmpDir))
        if data is None:
            input_arg = ''
        else:
            input_arg = getattr(self,input_handler)(data)

        training_data = self.PositionalParameters['-training-data']

        # Build up the command, consisting of a BaseCommand followed by
        # input and output (file) specifications
        command = self._commandline_join(
            [self.BaseCommand, input_arg, assignment_fp, training_data, 
             '>', outfile, '2>', errfile,]
            )

        if self.HaltExec: 
            raise AssertionError, "Halted exec with command:\n" + command
        # The return value of system is a 16-bit number containing the signal 
        # number that killed the process, and then the exit status. 
        # We only want to keep the exit status so do a right bitwise shift to 
        # get rid of the signal number byte
        exit_status = system(command) >> 8
      
        # Determine if error should be raised due to exit status of 
        # appliciation
        if not self._accept_exit_status(exit_status):
            raise ApplicationError, \
             'Unacceptable application exit status: %s, command: %s'\
                % (str(exit_status),command)
        
        # open the stdout and stderr if not being suppressed
        out = None
        if not suppress_stdout:
            out = open(outfile,"r")
        err = None        
        if not suppress_stderr:
            err = open(errfile,"r")

        result_paths = self._get_result_paths(data)
        result_paths['Assignments'] = ResultPath(assignment_fp)
        result = CommandLineAppResult(
            out, err, exit_status, result_paths=result_paths)

        # Clean up the input file if one was created
        if remove_tmp:
            if self._input_filename:
                remove(self._input_filename)
                self._input_filename = None

        return result

    def _accept_exit_status(self, status):
        """Returns false if an error occurred in execution
        """
        return (status == 0)

    def _error_on_missing_application(self,params):
        """Raise an ApplicationNotFoundError if the app is not accessible
        """
        command = self._get_jar_fp()
        if not exists(command):
            raise ApplicationNotFoundError,\
             "Cannot find jar file. Is it installed? Is $RDP_JAR_PATH"+\
             " set correctly?"

    def _get_jar_fp(self):
        """Returns the full path to the JAR file.

        Raises an ApplicationError if the JAR file cannot be
        found in the (1) current directory or (2) the path specified
        in the RDP_JAR_PATH environment variable.
        """
        # handles case where the jar file is in the current working directory
        if exists(self._command):
            return self._command
        # handles the case where the user has specified the location via
        # an environment variable
        elif 'RDP_JAR_PATH' in environ:
            return getenv('RDP_JAR_PATH')
        # error otherwise
        else:
            raise ApplicationError,\
             "$RDP_JAR_PATH is not set -- this must be set to use the"+\
             " RDP classifier application controller."

    # Overridden to pull out JVM-specific command-line arguments.
    def _get_base_command(self):
        """Returns the base command plus command-line options.

        Does not include input file, output file, and training set.
        """
        # Necessary? Preserve for consistency.
        if self._command is None:
            raise ApplicationError, '_command has not been set.'

        # Append a change directory to the beginning of the command to change 
        # to self.WorkingDir before running the command
        # WorkingDir should be in quotes -- filenames might contain spaces
        cd_command = ''.join(['cd ',str(self.WorkingDir),';'])

        jvm_command = "java"
        jvm_arguments = self._commandline_join(self.JvmParameters.values())
        jar_arguments = '-jar "%s"' % self._get_jar_fp()

        result = self._commandline_join(
            [cd_command, jvm_command, jvm_arguments, jar_arguments]
            )
        return result
    
    BaseCommand = property(_get_base_command)

    def _commandline_join(self, tokens):
        """Formats a list of tokens as a shell command

        This seems to be a repeated pattern; may be useful in
        superclass.
        """
        commands = filter(None, map(str, tokens))
        return self._command_delimiter.join(commands).strip()

    @property
    def JvmParameters(self):
        return self.__extract_parameters('jvm')

    @property
    def PositionalParameters(self):
        return self.__extract_parameters('positional')

    def __extract_parameters(self, name):
        """Extracts parameters in self._<name>_parameters from self.Parameters

        Allows the program to conveniently access a subset of user-
        adjusted parameters, which are stored in the Parameters
        attribute.
        
        Relies on the convention of providing dicts named according to
        "_<name>_parameters" and "_<name>_synonyms".  The main
        parameters object is expected to be initialized with the
        contents of these dicts.  This method will throw an exception
        if either convention is not adhered to.
        """
        parameters = getattr(self, '_' + name + '_parameters')
        synonyms   = getattr(self, '_' + name + '_synonyms')
        result = Parameters(parameters, synonyms)
        for key in result.keys():
            result[key] = self.Parameters[key]
        return result


class RdpTrainer(RdpClassifier):
    _input_handler = '_input_as_lines'
    TrainingClass = 'edu.msu.cme.rdp.classifier.train.ClassifierTraineeMaker'
    PropertiesFile = 'RdpClassifier.properties'

    _rdp_parameters = {
        'taxonomy_file': ValuedParameter(None, None, IsPath=True),
        'model_output_dir': ValuedParameter(None, None, IsPath=True),
        'training_set_id': ValuedParameter(None, None, Value='1'),
        'taxonomy_version': ValuedParameter(None, None, Value='version1'),
        'modification_info': ValuedParameter(None, None, Value='cogent'),
        }
    _jvm_parameters = {
        # Maximum heap size for JVM.
        '-Xmx': ValuedParameter('-', Name='Xmx', Delimiter='', Value='1000m'),
        }
    _parameters = {}
    _parameters.update(_rdp_parameters)
    _parameters.update(_jvm_parameters)

    def _get_base_command(self):
        """Returns the base command plus command-line options.

        Does not include input file, output file, and training set.
        """
        cd_command = ''.join(['cd ', str(self.WorkingDir), ';'])
        jvm_command = "java"
        jvm_args = self._commandline_join(
            [self.Parameters[k] for k in self._jvm_parameters])
        cp_args = '-cp "%s" %s' % (self._get_jar_fp(), self.TrainingClass)

        command_parts = [cd_command, jvm_command, jvm_args, cp_args]
        return self._commandline_join(command_parts).strip()
    
    BaseCommand = property(_get_base_command)

    def _set_input_handler(self, method_name):
        """Stores the selected input handler in a private attribute.
        """
        self.__InputHandler = method_name

    def _get_input_handler(self):
        return '_input_handler_decorator'

    InputHandler = property(_get_input_handler, _set_input_handler)

    @property
    def ModelDir(self):
        return os.path.abspath(self.Parameters['model_output_dir'])

    def _input_handler_decorator(self, data):
        """Appends trailing parameters to selected input_handler's results.
        """
        input_handler = getattr(self, self.__InputHandler)
        input_parts = [
            self.Parameters['taxonomy_file'],
            input_handler(data),
            self.Parameters['training_set_id'],
            self.Parameters['taxonomy_version'],
            self.Parameters['modification_info'],
            self.ModelDir,
            ]
        return self._commandline_join(input_parts)

    def _get_result_paths(self, output_dir):
        self._write_properties_file()
        training_files = {
            'bergeyTree': 'bergeyTrainingTree.xml',
            'probabilityList': 'genus_wordConditionalProbList.txt',
            'probabilityIndex': 'wordConditionalProbIndexArr.txt',
            'wordPrior': 'logWordPrior.txt',
            'properties': self.PropertiesFile,
        }
        result_paths = {}
        for key, filename in training_files.iteritems():
            result_paths[key] = ResultPath(
                Path=os.path.join(self.ModelDir, filename), IsWritten=True)
        return result_paths
    
    def _write_properties_file(self):
        # The properties file specifies the names of the files in the
        # training directory.  We use the example properties file
        # directly from the rdp_classifier distribution, which lists
        # the default set of files created by the application.  We
        # must write this file manually after generating the
        # training data.
        properties_fp = os.path.join(self.ModelDir, self.PropertiesFile)
        properties_file = open(properties_fp, 'w')
        properties_file.write(
            "# Sample ResourceBundle properties file\n"
            "bergeyTree=bergeyTrainingTree.xml\n"
            "probabilityList=genus_wordConditionalProbList.txt\n"
            "probabilityIndex=wordConditionalProbIndexArr.txt\n"
            "wordPrior=logWordPrior.txt\n"
            "classifierVersion=Naive Bayesian rRNA Classifier Version 1.0, "
            "November 2003\n"
            )
        properties_file.close()


def parse_command_line_parameters(argv=None):
    """ Parses command line arguments """
    usage =\
     'usage: %prog [options] input_sequences_filepath'
    version = 'Version: %prog ' +  __version__
    parser = OptionParser(usage=usage, version=version)
          
    parser.add_option('-o','--output_fp',action='store',\
          type='string',dest='output_fp',help='Path to store '+\
          'output file [default: generated from input_sequences_filepath]')
          
    parser.add_option('-c','--min_confidence',action='store',\
          type='float',dest='min_confidence',help='minimum confidence '+\
          'level to return a classification [default: %default]')

    parser.set_defaults(verbose=False,min_confidence=0.80)

    opts, args = parser.parse_args(argv)
    if len(args) != 1:
       parser.error('Exactly one argument is required.')

    return opts, args


def assign_taxonomy(
    data, min_confidence=0.80, output_fp=None, training_data_fp=None,
    fixrank=True):
    """Assign taxonomy to each sequence in data with the RDP classifier
    
        data: open fasta file object or list of fasta lines
        confidence: minimum support threshold to assign taxonomy to a sequence
        output_fp: path to write output; if not provided, result will be 
         returned in a dict of {seq_id:(taxonomy_assignment,confidence)}
    """
    # Going to iterate through this twice in succession, best to force
    # evaluation now
    data = list(data)

    # RDP classifier doesn't preserve identifiers with spaces
    # Use lookup table
    seq_id_lookup = {}
    for seq_id, seq in MinimalFastaParser(data):
        seq_id_lookup[seq_id.split()[0]] = seq_id
    
    app = RdpClassifier()

    temp_output_file = tempfile.NamedTemporaryFile(
        prefix='RdpAssignments_', suffix='.txt')
    app.Parameters['-o'].on(temp_output_file.name)
    if training_data_fp is not None:
        app.Parameters['-t'].on(training_data_fp)
    if fixrank:
        app.Parameters['-f'].on('fixrank')

    app_result = app(data)

    assignments = {}

    # ShortSequenceException messages are written to stdout
    # Tag these ID's as unassignable
    for line in app_result['StdOut']:
        excep = parse_rdp_exception(line)
        if excep is not None:
            _, rdp_id = excep
            orig_id = seq_id_lookup[rdp_id]
            assignments[orig_id] = ('Unassignable', 1.0)
    
    for line in app_result['Assignments']:
        rdp_id, direction, taxa = parse_rdp_assignment(line)
        orig_id = seq_id_lookup[rdp_id]
        lineage, confidence = get_rdp_lineage(taxa, min_confidence)
        if lineage:
            assignments[orig_id] = (';'.join(lineage), confidence)
        else:
            assignments[orig_id] = ('Unclassified', 1.0)

    if output_fp:
        try:
            output_file = open(output_fp, 'w')
        except OSError:
            raise OSError("Can't open output file for writing: %s" % output_fp)
        for seq_id, assignment in assignments.items():
            lineage, confidence = assignment
            output_file.write(
                '%s\t%s\t%1.3f\n' % (seq_id, lineage, confidence))
        output_file.close()
        return None
    else:
        return assignments


def train_rdp_classifier(training_seqs_file, taxonomy_file, model_output_dir):
    """ Train RDP Classifier, saving to model_output_dir

        training_seqs_file, taxonomy_file: file-like objects used to
            train the RDP Classifier (see RdpTrainer documentation for
            format of training data)

        model_output_dir: directory in which to save the files
            necessary to classify sequences according to the training
            data

    Once the model data has been generated, the RDP Classifier may 
    """
    app = RdpTrainer()
    
    temp_taxonomy_file = tempfile.NamedTemporaryFile(
        prefix='RdpTaxonomy_', suffix='.txt')
    temp_taxonomy_file.write(taxonomy_file.read())
    temp_taxonomy_file.seek(0)

    app.Parameters['taxonomy_file'] = temp_taxonomy_file.name
    app.Parameters['model_output_dir'] = model_output_dir
    return app(training_seqs_file)


def train_rdp_classifier_and_assign_taxonomy(
    training_seqs_file, taxonomy_file, seqs_to_classify, min_confidence=0.80, 
    model_output_dir=None, classification_output_fp=None):
    """ Train RDP Classifier and assign taxonomy in one fell swoop

    The file objects training_seqs_file and taxonomy_file are used to
    train the RDP Classifier (see RdpTrainer documentation for
    details).  Model data is stored in model_output_dir.  If
    model_output_dir is not provided, a temporary directory is created
    and removed after classification.

    The sequences in seqs_to_classify are classified according to the
    model and filtered at the desired confidence level (default:
    0.80).

    The results are saved to classification_output_fp if provided,
    otherwise a dict of {seq_id:(taxonomy_assignment,confidence)} is
    returned.
    """
    if model_output_dir is None:
        training_dir = tempfile.mkdtemp(prefix='RdpTrainer_')
    else:
        training_dir = model_output_dir

    training_results = train_rdp_classifier(
        training_seqs_file, taxonomy_file, training_dir)
    training_data_fp = training_results['properties'].name
    assignment_results = assign_taxonomy(
        seqs_to_classify, min_confidence=min_confidence, 
        output_fp=classification_output_fp, training_data_fp=training_data_fp)

    if model_output_dir is None:
        rmtree(training_dir)

    return assignment_results


def get_rdp_lineage(rdp_taxa, min_confidence):
    lineage = []
    obs_confidence = 1.0
    for taxon, rank, confidence in rdp_taxa:
        if confidence >= min_confidence:
            obs_confidence = confidence
            lineage.append(taxon)
        else:
            break
    return lineage, obs_confidence


def parse_rdp_exception(line):
    if line.startswith('ShortSequenceException'):
        matchobj = re.search('recordID=(\S+)', line)
        if matchobj:
            rdp_id = matchobj.group(1)
            return ('ShortSequenceException', rdp_id)
    return None


def parse_rdp_assignment(line):
    """Returns a list of assigned taxa from an RDP classification line
    """
    toks = line.strip().split('\t')
    seq_id = toks.pop(0)
    direction = toks.pop(0)
    if ((len(toks) % 3) != 0):
        raise ValueError(
            "Expected assignments in a repeating series of (rank, name, "
            "confidence), received %s" % toks)
    assignments = []
    # Fancy way to create list of triples using consecutive items from
    # input.  See grouper function in documentation for itertools for
    # more general example.
    itoks = iter(toks)
    for taxon, rank, confidence_str in zip(itoks, itoks, itoks):
        if not taxon:
            continue
        assignments.append((taxon.strip('"'), rank, float(confidence_str)))
    return seq_id, direction, assignments


if __name__ == "__main__":    
    opts, args = parse_command_line_parameters()
    assign_taxonomy(
        open(args[0]), min_confidence=opts.min_confidence,
        output_fp=opts.output_fp)

