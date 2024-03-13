#!/usr/bin/python3

import os
import sys
import time
# XXX: abstract this
import solv
import Deptool
from werkzeug.exceptions import HTTPException

from flask import Flask, request, session, url_for, redirect, \
     send_from_directory, jsonify, \
     render_template, send_file, abort, g, flash
#from flask_bootstrap import Bootstrap
from flask import json

from xdg.BaseDirectory import save_cache_path

app = Flask(__name__)
app.config.from_object(__name__)
#Bootstrap(app)
#app.config['BOOTSTRAP_SERVE_LOCAL'] = True

class GJSONProvider(json.provider.DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, solv.XSolvable):
            return { str(o): Deptool.Deptool._solvable2dict(o) }

        if isinstance(o, solv.Problem):
            return str(o)

        return super().default(o)

app.json_provider_class = GJSONProvider
app.json = GJSONProvider(app)

@app.errorhandler(HTTPException)
def handle_exception(e):
    response = e.get_response()
    # replace the body with JSON
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response

@app.errorhandler(Deptool.DeptoolException)
def handle_exception(e):
    app.logger.error("caught exception: %s", str(e));
    response = jsonify({'message': str(e)})
    response.status_code = 400
    return response

@app.template_filter('solvable_size')
def solvable_size(s):
    return s.lookup_num(solv.SOLVABLE_INSTALLSIZE)

@app.route('/')
def list():

    d = Deptool.Deptool()

    return render_template('index.html', d = d)

@app.route('/distribution', methods=['GET'])
def distribution():

    d = Deptool.Deptool()

    name = request.args.get('name')
    if name is None:
        return jsonify(d.context_list())

    return jsonify(d.context_info(name))

@app.route('/solve', methods=['POST'])
def solve():

    distribution = request.args.get('distribution')
    if distribution is None:
        raise Deptool.DeptoolException("missing distribution")

    if request.content_length > 2048:
        raise Deptool.DeptoolException("request too large")

    data = request.get_data(as_text=True)
    if data is None:
        raise Deptool.DeptoolException("missing data")

    d = Deptool.Deptool(context=distribution)
    app.logger.debug("got job %s", data);

    result = d.process_testcase(data.split('\n'))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = save_cache_path('opensuse.org', 'deptool', 'solve')

    with open(os.path.join(path, 'job-{}.json'.format(stamp)), 'w') as fh:
        s = dict(distibution = distribution, job = data, version="1")
        fh.write(json.dumps(s))

#    with open(os.path.join(path, 'result-{}.json'.format(stamp)), 'w') as fh:
#        s = dict(result = result, version="1")
#        fh.write(json.dumps(result))

    if 'text/uri-list' in request.accept_mimetypes.best:
        return '\n'.join(d.result_as_urls(result))+"\n", 200, { 'Content-Type': 'text/uri-list' }

    if 'application/metalink4+xml' in request.accept_mimetypes.best:
        return d.result_as_metalink(result), 200, { 'Content-Type': 'application/metalink4+xml' }

    if request.accept_mimetypes.accept_json:
        return jsonify(result)

    raise Deptool.DeptoolException("invalid format")

@app.route('/install/<string:context>')
def install(context):
    d = Deptool.Deptool(context=context)
    packages = request.args.getlist('package')
    norecommends = request.args.get('norecommends', False)
    result = None
    if packages:
        packages = [p for p in packages if p and p != '']
        app.logger.info(packages)
        if len(packages):
            result = d.solve(packages, ignore_recommended = norecommends)
    return render_template('install.html', context = context, packages=packages, result = result, norecommends = norecommends)

@app.route('/info')
def info():
    context = request.args.get('context', None)
    arch = request.args.get('arch', None)
    repos = request.args.getlist('repo[]')

    package = request.args.get('package', None)
    if not (context and package):
        raise Deptool.DeptoolException("missing parameters")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    if arch:
        d.arch = arch
    result = d.info(package)

    return jsonify(result)

@app.route('/search')
def search():
    context = request.args.get('context', None)
    arch = request.args.get('arch', None)
    repos = request.args.getlist('repo[]')
    provides = request.args.get('provides', None)
    if provides is not None and provides == '1':
        provides = True
    else:
        provides = False

    text = request.args.get('text', None)
    if not (context and text):
        raise Deptool.DeptoolException("missing parameters")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    result = d.search(text, provides=provides)

    return jsonify(result)


@app.route('/whatprovides')
def whatprovides():
    context = request.args.get('context', None)
    arch = request.args.get('arch', None)
    repos = request.args.getlist('repo[]')
    relation = request.args.get('relation', None)
    if not (context and relation):
        raise Deptool.DeptoolException("missing relation parameter")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    result = d.whatprovides(relation)

    return jsonify(result)

@app.route('/rdeps')
def rdeps_json():
    context = request.args.get('context', None)
    arch = request.args.get('arch', None)
    repos = request.args.getlist('repo[]')

    solvable = request.args.get('solvable', None)
    if not (context and solvable):
        raise Deptool.DeptoolException("missing parameters")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    result = d.rdeps(solvable)

    return jsonify(result)

@app.route('/depinfo')
def depinfo_json():
    context = request.args.get('context', None)
    arch = request.args.get('arch', None)
    repos = request.args.getlist('repo[]')

    relation = request.args.get('relation', None)
    if not (context and relation):
        raise Deptool.DeptoolException("missing parameters")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    result = d.depinfo(relation)

    return jsonify(result)

@app.route('/refresh', methods=['POST'])
def refresh():
    context = request.args.get('context', None)
    if not context:
        raise Deptool.DeptoolException("missing parameters")

    d = Deptool.Deptool(context=context)
    d.refresh_repos()

    return jsonify({'message': '%s refreshed successfully'%(context)})


@app.route('/info/<string:context>/<string:package>')
def info_path(context, package):
    arch = request.args.get('arch', None)
    d = Deptool.Deptool(context=context)
    d.arch = arch
    result = d.info(package)

    if (request.args.get('format','') == 'json'):
        return jsonify(result)

    return render_template('info.html', context = context, package = package, result = result)

@app.route('/rdeps/<string:context>/<string:package>')
def rdeps(context, package):

    d = Deptool.Deptool(context=context)
    result = d.rdeps(package)

    return render_template('rdeps.html', context = context, package = package, result = result)

@app.route('/depinfo/<string:context>', methods=['GET'])
def depinfo(context):

    relation = request.args.get('relation')
    if relation is None:
        raise Deptool.DeptoolException("missing relation parameter")

    d = Deptool.Deptool(context=context)
    result = d.depinfo(relation)

    return render_template('depinfo.html', context = context, relation = relation, result = result)


@app.route('/awesome/<path:filename>')
def awesome(filename):
    return send_from_directory('/usr/share/fontawesome-web', filename)


application = app
if __name__ == '__main__':
    application.run(debug=True)

