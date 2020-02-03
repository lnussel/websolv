#!/usr/bin/python3

from pprint import pprint
import os
import sys
import re
import logging
import cmdln

from fnmatch import fnmatch
from configparser import SafeConfigParser
import solv
import rpm

DATA_DIR = os.path.dirname(os.path.realpath(__file__))

logger = None

REASONS = dict([(getattr(solv.Solver, i), i[14:]) for i in dir(solv.Solver) if i.startswith('SOLVER_REASON_')])

SOLVERFLAGS = dict([(i[12:].lower().replace('_', ''), getattr(solv.Solver, i)) for i in dir(solv.Solver) if i.startswith('SOLVER_FLAG_')])

class DeptoolException(Exception):
    pass

class ParseError(DeptoolException):
    pass

class PackageNotFound(DeptoolException):
    pass


# fully qualified package name of a solvable ie name-evr.arch
def fqpn(s):
    return '{}-{}.{}'.format(s.name, s.evr, s.arch)

class Deptool(object):

    def __init__(self):
        self.arch = None
        self.context = None
        self.with_system = None
        self.pool = None

    def context_list(self):
        d = DATA_DIR + "/deptool"
        return sorted([os.path.basename(f) for f in os.listdir(d) if os.path.isdir(os.path.join(d, f))])

    def context_info(self, context):
        result = {}

        settings = SafeConfigParser()
        settings.read('/'.join((DATA_DIR, 'deptool', context, 'settings.conf')))

        for key in settings['global']:
            if key == 'arch':
                result[key] = settings['global'][key].split(' ')
            else:
                result[key] = settings['global'][key]

        result['repos'] = {}
        for config in self._read_repos(context):
            name = config.sections()[0]
            repo = {}
            for key in config[name]:
                if key.startswith('.'):
                    continue
                repo[key] = config[name][key]
            result['repos'][name] = repo

        return result

    def prepare_pool(self, repos = None, with_system = False):

        self.pool = solv.Pool()
        self.pool.setarch(self.arch)

        self.add_repos(repos)

        if self.with_system:
            self._add_system_repo()

        self.pool.addfileprovides()
        self.pool.createwhatprovides()

    def _read_repos(self, context, repos = None):

        repodir = DATA_DIR + "/deptool/%s/repos"%context
        solvfile = DATA_DIR + '/deptool/%s/.cache/zypp/solv/%%s/solv'%context

        if not repos:
            repos = [f for f in os.listdir(repodir) if fnmatch(f, '*.repo')]

        for r in repos:
            if r.endswith('.repo'):
                name = os.path.splitext(r)[0]
            else:
                name = r
                r += '.repo'

            config = SafeConfigParser()
            config.read('/'.join((repodir, r)))
            if not name in config:
                logger.error("missing section {} in {}".format(name, r))
                continue

            config[name]['.solv'] = solvfile % name
            yield config

    def add_repos(self, repos = None):

        for config in self._read_repos(self.context, repos):
            name = config.sections()[0]
            if repos == None and config.get(name, 'enabled') != '1':
                continue
            repo = self.pool.add_repo(name)
            repo.add_solv(config[name]['.solv'])
            if config.has_option(name, 'priority'):
                repo.priority = config.getint(name, 'priority')
            logger.debug("add repo %s: %s", name, config[name]['.solv'])

    def _add_system_repo(self):
        solvfile = '/var/cache/zypp/solv/@System/solv'
        repo = self.pool.add_repo('system')
        repo.add_solv(solvfile)

    def process_testcase(self, lines):

        prepared = False
        jobs = []

        self.pool = solv.Pool()
        solver = None

        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                continue
            if not line:
                continue

            tokens = line.split()

            if tokens[0] == 'distribution' and len(tokens) == 2:
                prepared = False
                if self.context:
                    raise ParseError("distribution already defined")
                self.context = tokens[1]
                self.add_repos()
            elif tokens[0] == 'system' and len(tokens) >= 3:
                prepared = False
                if tokens[2] != 'rpm':
                    raise ParseError("only disttype rpm supporte")
                self.pool.setdisttype(solv.Pool.DISTTYPE_RPM)
                logger.debug("dist type {}".format(tokens[2]))
                if tokens[1] == 'unset' or tokens[1] == '-':
                    self.pool.setarch(0)
                elif tokens[1][0] == ':':
                    self.pool.setarchpolicy(tokens[1][1:])
                else:
                    self.pool.setarch(str(tokens[1]))
                    logger.debug("arch {}".format(tokens[1]))
                if len(tokens) > 3:
                    raise ParseError('invalid arch')

            elif tokens[0] == 'job' and len(tokens) > 1:
                if not prepared:
                    self.pool.addfileprovides()
                    self.pool.createwhatprovides()
                    prepared = True
                if tokens[1] == 'install' or tokens[1] == 'lock':
                    if tokens[2] == 'name':
                        n = str(tokens[3])
                        sel = self.pool.select(n, solv.Selection.SELECTION_NAME)
                        if sel.isempty():
                            raise PackageNotFound('package {} not found'.format(n))

                        if tokens[1] == 'install':
                            jobs += sel.jobs(solv.Job.SOLVER_INSTALL)
                        elif tokens[1] == 'lock':
                            jobs += sel.jobs(solv.Job.SOLVER_LOCK)

                        logger.debug("{} {}".format(tokens[1], n))
                    else:
                    # TODO
                        raise ParseError('invalid install selector {}'.format(tokens[2]))

            elif tokens[0] == 'solverflags' and len(tokens) > 1:

                if not solver:
                    solver = self.pool.Solver()

                # XXX: original parser also takes coma here
                for t in tokens[1:]:
                    v = 1
                    if t.startswith('!'):
                        v = 0
                        t = t[1:]
                    if t in SOLVERFLAGS:
                        logger.debug("setting solver flag {}={}".format(t, v))
                        solver.set_flag(SOLVERFLAGS[t], v)
                    else:
                        raise ParseError("invalid solverflag")
            else:
                raise ParseError("unkown instruction")

        if not prepared:
            self.pool.addfileprovides()
            self.pool.createwhatprovides()
            prepared = True

        if not solver:
            solver = self.pool.Solver()

        problems = solver.solve(jobs)

        return self.process_results(solver, problems)

    def solve(self, packages, ignore_recommended = False, locked = None, locale = None, filesystem = None):

        if not self.pool:
            self.prepare_pool()

        for l in locale or []:
            self.pool.set_namespaceproviders(solv.NAMESPACE_LANGUAGE, self.pool.Dep(l), True)

        for fs in filesystem or []:
            self.pool.set_namespaceproviders(solv.NAMESPACE_FILESYSTEM, self.pool.Dep(fs), True)


        jobs = []
        for l in locked or []:
            sel = self.pool.select(str(l), solv.Selection.SELECTION_NAME)
            if sel.isempty():
                # if we can't find it, it probably is not as important
                logger.debug('locked package {} not found'.format(l))
            else:
                jobs += sel.jobs(solv.Job.SOLVER_LOCK)

        for n in packages:
            sel = self.pool.select(str(n), solv.Selection.SELECTION_NAME)
            if sel.isempty():
                logger.error('package {} not found'.format(n))
            jobs += sel.jobs(solv.Job.SOLVER_INSTALL)

        solver = self.pool.Solver()

        if ignore_recommended:
            solver.set_flag(solver.SOLVER_FLAG_IGNORE_RECOMMENDED, 1)

        problems = solver.solve(jobs)

        return self.process_results(solver, problems)

    def process_results(self, solver, problems):

        result = {}

        if problems:
            # XXX: need to convert to string here as solver goes out of scope
            # so the conversion would crash later
            result['problems'] = [str(p) for p in problems]
            for problem in problems:
                logger.error('%s', problem)
            return result

        trans = solver.transaction()
        if trans.isempty():
            logger.error('nothing to do')
            return result

        newsolvables = []
        choices = []
        for s in trans.newsolvables():
            reason, rule = solver.describe_decision(s)
            if reason == solv.Solver.SOLVER_REASON_WEAKDEP:
                for v in solver.describe_weakdep_decision(s):
                    reason2, s2, dep = v
                    target = s2
                    if reason2 == solver.SOLVER_REASON_SUPPLEMENTED:
                        target = s
                    newsolvables.append((s, REASONS[reason], [[target, REASONS[reason2], dep.str()]]))
            else:
                infos = []
                if rule:
                    rt2str = {}
                    for rt in dir(solver):
                        if rt.startswith("SOLVER_RULE_"):
                            rt2str[getattr(solver, rt)] = rt[len('SOLVER_RULE_'):]
                    for ri in rule.allinfos():
                        if ri.type == solver.SOLVER_RULE_JOB:
                            # info doesn't seem to be useful for that one
                            continue
                        infos.append((ri.solvable, rt2str[ri.type], ri.dep.str(), ri.othersolvable))
                        if (reason == solver.SOLVER_REASON_RESOLVE):
                            choices.append(ri.dep.str())
                newsolvables.append((s, REASONS[reason], infos))

        result['newsolvables'] = newsolvables
        result['choices'] = choices
        # XXX: is this correct?
        result['size'] = trans.calc_installsizechange() * 1024

        return result

    @classmethod
    def _solvable2dict(cls, s, deps = False):
        sattrs = [s for s in dir(solv) if s.startswith("SOLVABLE_")]
        result = {}
        for attr in sattrs:
            sid = getattr(solv, attr, 0)
            # pretty stupid, just lookup strings and numbers
            value = s.lookup_str(sid)
            if value:
                result[attr[len('SOLVABLE_'):]] = value
            else:
                value = s.lookup_num(sid)
                if value:
                    result[attr[len('SOLVABLE_'):]] = value

            if deps:
                for kind in ('RECOMMENDS', 'REQUIRES', 'SUPPLEMENTS', 'ENHANCES', 'PROVIDES', 'SUGGESTS'):
                    deps = s.lookup_deparray(getattr(solv, 'SOLVABLE_' + kind), 0)
                    if deps:
                        deplist = []
                        for dep in deps:
                            deplist.append('{}'.format(dep))
                        result[kind] = deplist

        return result

    def info(self, package, deps = True):

        if not self.pool:
            self.prepare_pool()

        result = {}

        flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_PROVIDES|solv.Selection.SELECTION_GLOB
        flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_REL
        sel = self.pool.select(package, flags)
        if sel.isempty():
            logger.error("%s not found", package)
            return result

        for s in sel.solvables():
            result[str(s)] = self._solvable2dict(s, deps)

        return result


    def whatprovides(self, r):

        if not self.pool:
            self.prepare_pool()

        result = []
        # XXX: cut off complex statements
        # would need something like testcase_str2dep()
        r = r.split(' ')[0]
        i = self.pool.str2id(r)
        for s in self.pool.whatprovides(i):
            result.append(s)

        return result


    def rdeps(self, package, providers = True):

        if not self.pool:
            self.prepare_pool()

        result = {}

        kinds = ['RECOMMENDS', 'REQUIRES', 'SUPPLEMENTS', 'ENHANCES', 'SUGGESTS']
        if providers:
            kinds.append('PROVIDES')

        for kind in kinds:
            kindid = getattr(solv, 'SOLVABLE_' + kind, 0)
            flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_GLOB
            flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH
            sel = self.pool.select(package, flags)
            if sel.isempty():
                logger.error("%s not found", package)
                continue
            for s in sel.solvables():
                prov = s.lookup_deparray(solv.SOLVABLE_PROVIDES, 0)
                if not prov:
                    logger.error("%s doesn't provide anything")
                    continue
                for p in prov:
                    sel = self.pool.matchdepid(p, solv.Selection.SELECTION_REL | solv.Selection.SELECTION_FLAT, kindid, 0)
                    if sel.isempty():
                        logger.debug('nothing %s %s', kind.lower(), p)
                        continue
                    for r in sel.solvables():
                        if kindid == solv.SOLVABLE_PROVIDES and r == s:
                            continue
                        result.setdefault(kind, {}).setdefault(p, []).append('{}-{}.{}'.format(r.name, r.evr, r.arch))

        return result

    def depinfo(self, relation):

        if not self.pool:
            self.prepare_pool()

        result = {}

        kinds = ['PROVIDES', 'RECOMMENDS', 'REQUIRES', 'SUPPLEMENTS', 'ENHANCES', 'SUGGESTS']

        # FIXME: need to parse relation
        p = self.pool.str2id(relation)
        for kind in kinds:
            kindid = getattr(solv, 'SOLVABLE_' + kind, 0)
            sel = self.pool.matchdepid(p, solv.Selection.SELECTION_REL | solv.Selection.SELECTION_FLAT, kindid, 0)
            if sel.isempty():
                logger.debug('nothing %s %s', kind.lower(), p)
                continue
            for r in sel.solvables():
                result.setdefault(kind,[]).append(fqpn(r))

        return result

class CommandLineInterface(cmdln.Cmdln):
    def __init__(self, *args, **kwargs):
        cmdln.Cmdln.__init__(self, args, kwargs)
        self.d = None

    def get_optparser(self):
        parser = cmdln.CmdlnOptionParser(self)
        parser.add_option("--dry", action="store_true", help="dry run")
        parser.add_option("--debug", action="store_true", help="debug output")
        parser.add_option("--verbose", action="store_true", help="verbose")
        parser.add_option("--system", action="store_true", help="with system repo")
        parser.add_option("--arch", dest="arch", help="architecture", default='x86_64')
        parser.add_option("--context", '-C', dest="context", help="context to use ('list' to list known ones)")
        return parser

    def postoptparse(self):
        level = None
        if self.options.debug:
            level = logging.DEBUG
        elif self.options.verbose:
            level = logging.INFO

        logging.basicConfig(level=level)

        global logger
        logger = logging.getLogger()

        self.d = Deptool()
        self.d.arch = self.options.arch
        self.d.context = self.options.context
        self.d.with_system = self.options.system

        if self.options.context and self.options.context == 'list':
            print('\n'.join(self.d.context_list()))
            sys.exit(0)

    @cmdln.option("-s", "--single", action="store_true",
                  help="single step all requires/recommends")
    @cmdln.option("--size", action="store_true",
                  help="print installed size")
    @cmdln.option("-l", "--lock", dest="lock", action="append",
                  help="packages to lock")
    @cmdln.option("--explain", dest="explain", action="append",
                  help="rule to explain")
    @cmdln.option("--solver-debug", action="store_true",
                  help="debug solver")
    @cmdln.option("--ignore-recommended", action="store_true",
                  help="ignore recommended")
    @cmdln.option("-L", "--locale", dest="locale", action="append",
                  help="locale")
    @cmdln.option("-F", "--filesytem", dest="filesystem", action="append",
                  help="filesystem to use")
    def do_install(self, subcmd, opts, *args):
        """${cmd_name}: generate pot file for patterns

        ${cmd_usage}
        ${cmd_option_list}
        """

        locked = []
        if opts.lock:
            for l in opts.lock:
                for i in l.split(','):
                    locked.append(i)

        good = True

        self.d.prepare_pool()
        if opts.solver_debug:
            self.d.pool.set_debuglevel(3)

        def solveit(packages):

            result = self.d.solve(packages, opts.ignore_recommended, locked, opts.locale, opts.filesystem)

            if 'newsolvables' in result:
                for s in result['newsolvables']:
                    if opts.size:
                        print(s[0].lookup_num(solv.SOLVABLE_INSTALLSIZE), s[0].name, ','.join(packages))
                    else:
                        print(s[0].name, ','.join(packages))
                    if opts.explain and (s[0].name in opts.explain or '*' in opts.explain):
                        print("-> %s" % (s[1]))
                        for rule in s[2]:
                            print('   * '+' '.join([str(i) for i in rule if i is not None]))

                if opts.size:
                    print("%s TOTAL" % (result['size']))

            return True

        if opts.single:
            for n in args:
                sel = self.d.pool.select(str(n), solv.Selection.SELECTION_NAME)
                for s in sel.solvables():
                    deps = s.lookup_deparray(solv.SOLVABLE_RECOMMENDS)
                    deps += s.lookup_deparray(solv.SOLVABLE_REQUIRES)
                    for dep in deps:
                        # only add recommends that exist as packages
                        rec = self.d.pool.select(dep.str(), solv.Selection.SELECTION_NAME)
                        if not rec.isempty():
                            if not solveit([dep.str()]):
                                good = False
        else:
            if not solveit(args):
                good = False

        if not good:
            logger.error("solver errors encountered")
            return 1

    def do_deps(self, subcmd, opts, *packages):
        """${cmd_name}: show package deps

        ${cmd_usage}
        ${cmd_option_list}
        """

        self.d.prepare_pool()

        for n in packages:
            sel = self.d.pool.select(n, solv.Selection.SELECTION_NAME)
            if sel.isempty():
                logger.error("%s not found", n)
            for s in sel.solvables():
                print('- {}-{}@{}:'.format(s.name, s.evr, s.arch))
                for kind in ('RECOMMENDS', 'REQUIRES', 'SUPPLEMENTS', 'ENHANCES', 'PROVIDES', 'SUGGESTS'):
                    deps = s.lookup_deparray(getattr(solv, 'SOLVABLE_' + kind), 0)
                    if deps:
                        print('  {}:'.format(kind))
                        for dep in deps:
                            print('    - {}'.format(dep))

    @cmdln.option("-r", "--repo", dest="repo", action="append",
                  help="repo to use")
    @cmdln.option("--source", action="store_true",
                  help="print source rpm")
    def do_whatprovides(self, subcmd, opts, *relation):
        """${cmd_name}: list packages providing given relations

        ${cmd_usage}
        ${cmd_option_list}
        """

        self.d.prepare_pool()

        for r in relation:
            i = self.d.pool.str2id(r)
            for s in self.d.pool.whatprovides(i):
                if opts.source:
                    src = s.name
                    if not s.lookup_void(solv.SOLVABLE_SOURCENAME):
                        src = s.lookup_str(solv.SOLVABLE_SOURCENAME)
                    print(src)
                else:
                    print('- {}-{}@{}:'.format(s.name, s.evr, s.arch))

    def do_patterns(self, subcmd, opts, *relation):
        """${cmd_name}: list patterns

        ${cmd_usage}
        ${cmd_option_list}
        """

        self.prepare_pool()

        patternid = self.d.pool.str2id('pattern()')
        for s in self.d.pool.whatprovides(patternid):
            deps = s.lookup_deparray(solv.SOLVABLE_PROVIDES)
            order = 0
            for dep in deps:
                name = str(dep)
                if name.startswith('pattern-order()'):
                    # XXX: no function in bindings to do that properly
                    order = name[name.find('= ') + 2:]
            print("{} {}".format(order, s.name))

    @cmdln.option("--providers", action="store_true",
                  help="also show other providers")
    @cmdln.option("--relation", action="store_true",
                  help="arguments are relations rather than package names")
    @cmdln.option("-r", "--repo", dest="repo", action="append",
                  help="repo to use")
    def do_rdeps(self, subcmd, opts, *args):
        """${cmd_name}: list packages that require, recommend etc the given packages

        ${cmd_usage}
        ${cmd_option_list}
        """

        for n in args:
            result = self.d.rdeps(n, providers = opts.providers)
            for kind in result.keys():
                print("{}:".format(kind))
                for symbol in result[kind].keys():
                    print("  {}:".format(symbol))
                    for n in result[kind][symbol]:
                        print("    - {}".format(n))

    def do_what(self, subcmd, opts, relation):
        """${cmd_name}: list packages that have dependencies on given relation

        ${cmd_usage}
        ${cmd_option_list}
        """

        result = self.d.depinfo(relation)
        if result:
            for n in result.keys():
                print(n)
                for s in result[n]:
                    print("  {}".format(s))

    @cmdln.option("--deps", action="store_true",
                  help="show deps too")
    def do_info(self, subcmd, opts, *args):
        """${cmd_name}: show some info about a package

        ${cmd_usage}
        ${cmd_option_list}
        """

        for n in args:
            result = self.d.info(n, deps = opts.deps)
            if result:
                for n in result.keys():
                    print(n)
                    for k, v in result[n].items():
                        print("  - {}: {}".format(k, v))

    @cmdln.option("--size", action="store_true",
                  help="print installed size")
    @cmdln.option("--explain", dest="explain", action="append",
                  help="rule to explain")
    def do_parse(self, subcmd, opts, filename):
        """${cmd_name}: generate pot file for patterns

        ${cmd_usage}
        ${cmd_option_list}
        """

        with open(filename, 'r') as fh:

            result = self.d.process_testcase(fh.readlines())

            if 'newsolvables' in result:
                for s in result['newsolvables']:
                    if opts.size:
                        print(s[0].lookup_num(solv.SOLVABLE_INSTALLSIZE), s[0].name)
                    else:
                        print(s[0].name)
                    if opts.explain and (s[0].name in opts.explain or '*' in opts.explain):
                        print("-> %s" % (s[1]))
                        for rule in s[2]:
                            print('   * '+' '.join([str(i) for i in rule if i is not None]))

                if opts.size:
                    print("%s TOTAL" % (result['size']))

if __name__ == "__main__":
    app = CommandLineInterface()
    sys.exit(app.main())
else:
    logger = logging.getLogger()
