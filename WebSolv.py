#!/usr/bin/python3

import os
import sys
# XXX: abstract this
import solv
import Deptool
from werkzeug.exceptions import HTTPException

from flask import Flask, request, session, url_for, redirect, \
     send_from_directory, jsonify, \
     render_template, send_file, abort, g, flash, _app_ctx_stack
#from flask_bootstrap import Bootstrap
from flask import json

app = Flask(__name__)
app.config.from_object(__name__)
#Bootstrap(app)
#app.config['BOOTSTRAP_SERVE_LOCAL'] = True

class GJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, solv.XSolvable):
            return { str(o): Deptool.Deptool._solvable2dict(o) }

        if isinstance(o, solv.Problem):
            return str(o)

        return json.JSONEncoder.default(self, o)

app.json_encoder = GJSONEncoder

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
        raise KeyError("missing distribution")

    if request.content_length > 2048:
        raise KeyError("request too large")

    data = request.get_data(as_text=True)
    if data is None:
        raise KeyError("missing data")

    d = Deptool.Deptool(context=distribution)
    app.logger.debug("got job %s", data);

    return jsonify(d.process_testcase(data.split('\n')))

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
        raise KeyError("missing parameters")

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
        raise KeyError("missing parameters")

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
        raise KeyError("missing relation parameter")

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
        raise KeyError("missing parameters")

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
        raise KeyError("missing parameters")

    d = Deptool.Deptool(context=context, arch=arch, repos=repos)
    result = d.depinfo(relation)

    return jsonify(result)

@app.route('/refresh', methods=['POST'])
def refresh():
    context = request.args.get('context', None)
    if not context:
        raise KeyError("missing parameters")

    d = Deptool.Deptool(context=context)
    d.refresh_repos()

    return jsonify({'message': 'ok'})


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
        raise KeyError("missing relation parameter")

    d = Deptool.Deptool(context=context)
    result = d.depinfo(relation)

    return render_template('depinfo.html', context = context, relation = relation, result = result)


@app.route('/awesome/<path:filename>')
def awesome(filename):
    return send_from_directory('/usr/share/font-awesome-web', filename)


application = app
if __name__ == '__main__':
    application.run(debug=True)

