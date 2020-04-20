$(document).ready(function() {
var $JOB_TEMPLATE;
var $REPO_TEMPLATE;
var CURRENT_DISTRO;

function get_distro() {
   return $('#distro_select').val();
}

function get_arch() {
   return $('#arch_select').val();
}

function setup_distro(info) {
  if (!get_distro() || !get_arch()) {
    show_error_popup('Error', 'Missing distro or arch');
    return;
  }

  if (!$JOB_TEMPLATE) {
    var $job = $('#solveform .job_template');
    //job.find('.solve_job_text').each(function() { this.value = '';});
    $JOB_TEMPLATE = $job.clone()
    $JOB_TEMPLATE.find('.solve_job_text').each(function() { this.value = '';});
    $job.find('.solve_job_trash_button').prop('disable', true);
    job_setup_callbacks($job);
  }
  if (!$REPO_TEMPLATE) {
    var $repo_template = $('#repolist div');
    $REPO_TEMPLATE = $repo_template.clone().removeClass('repo_list_template');
    $repo_template.remove();
  }


  if (info) {
    CURRENT_DISTRO = info;
    $("#repolist").empty();
    var num_repos = 0;
    $.each(info['repos'], function(name, props) {
      var $elem = $REPO_TEMPLATE.clone()
      $elem.find('input').attr('id', 'repo_checkbox_'+num_repos).prop('data-repo', name).prop('checked', props['enabled'] == '1');
      $elem.find('label').attr('for', 'repo_checkbox_'+num_repos).text(name);
      ++num_repos;
      $elem.appendTo("#repolist");
      $elem.show();
    });
  }

  $('#search_result').empty().hide();
  $('#solv_result').hide();
  $('#solv_spinner').hide();

  var l = window.location.hash;
  /*
  if (l == '#search' || l == '#solve') {
    $(l + '-tab').tab('show');
  } else
  if (l.startsWith('#info/')) {
    show_solvable_info(l.substr(('#info/').length));
  } else if (l.startsWith('#depinfo/')) {
    show_dep_info(l.substr(('#depinfo/').length));
  }
  */
}

function add_new_job(name = null) {
  var $elem = $JOB_TEMPLATE.clone()
  var $input = $elem.find('.solve_job_text');
  if (name) {
    $input.val(name)
  }
  $elem.insertBefore('#btn-add');
  job_setup_callbacks($elem);
  $input.focus();
}

function job_setup_callbacks($elem) {
  $elem.find('.dropdown-item').on('click', function () {
    name = $(this).text();
    $elem.find('.solve_job_button').text(name);
  });

  $elem.find('.solve_job_trash_button').on('click', function () {
    $elem.remove();
  });

  $elem.find('.solve_job_text').on('keypress', function (e) {
    if (e.which == 13) {
      e.preventDefault();
      solve();
    }
  });
}

function update_arch() {
  ep_distribution = $('#ep_distribution').attr('url');

  target = $("#arch_select");
  target.empty();

  $.get(ep_distribution + '?name=' + get_distro(), function(info, status) {

    archs = info['arch'];
    $.each(archs, function(i, v) {
      elem = $('<option value="'+v+'"></option>').text(v);
      target.append(elem);
    });

    setup_distro(info);
  });
}

function start() {
  ep_distribution = $('#ep_distribution').attr('url');
  $.get(ep_distribution, function(distros, status) {

    target = $("#distro_select");
    target.empty();

    target.on('change', function() {
      update_arch();
    });

    $('#arch_select').on('change', function() {
      setup_distro();
    });

    need_init_arch = false;
    $.each(distros, function(i, v) {
      elem = $('<option value="'+v+'"></option>').text(v);
      target.append(elem);
      if (v == 'Tumbleweed') {
	elem.attr('selected', 1);
	need_init_arch = true;
      }
    });

    if (need_init_arch) {
      update_arch();
    }

    $('#btn-refresh').on('click', function() {
      var ep_refresh = $('#ep_refresh').attr('url');

      $.post(ep_refresh + '?' + $.param({'context': get_distro()}), '', function(info, status) {
        show_info_popup('Repo refresh', info['message']);
      }, 'json')
      .fail(function(xhr, textStatus, error) {
        show_error_popup(error, JSON.parse(xhr.responseText)['message']);
      });
    });

    $('#btn-add').on('click', function() { add_new_job() });

    $('#btn-solve').on('click', function () { solve() });

    $('#btn-search').on('click', function() {
      search();
    })
    $('#search-text').on('keypress', function (e) {
      if (e.which == 13) {
        e.preventDefault();
        search();
      }
    });
    $('#searchform').submit(function (e) {
      e.preventDefault();
    });

    $('#btn-solve-search').on('click', function () {
      $('#search-tab').tab('show');
    });

    $('#page-function-tabs a[data-toggle="pill"]').on('shown.bs.tab', function (e) {
      // need to make sure the anchor doesn't match an existing one otherwise the page would scroll
      //window.location.replace(e.target['href'].replace('-pane', ''));
      var what = e.target['id'];
      if (what == 'search-tab') {
        $('#search-text').focus();
      } else if (what == 'solve-tab') {
        $('#solveform .solve_job_text').last().focus();
      }
    });

    $('#dep_info').on('hidden.bs.modal', function() { window.history.back() });
    $('#solvable_info').on('hidden.bs.modal', function() { window.history.back() });

    $("#search-tab").tab('show');
    $('#search-text').focus();
  });
}

function _show_popup($dialog, title, text) {
  $dialog.find('strong').text(title);
  $dialog.find('.toast-body').text(text);
  $dialog.toast('show');
}

function show_error_popup(title, text) {
  var $dialog = $('.toast');
  $dialog.find('.toast-header i').removeClass('fa-exclamation fa-info-circle').addClass('fa-exclamation');
  $dialog.find('.toast-header i').removeClass('text-danger text-success').addClass('text-danger');
  _show_popup($dialog, title, text);
}

function show_info_popup(title, text) {
  var $dialog = $('.toast');
  $dialog.find('.toast-header i').removeClass('fa-exclamation fa-info-circle').addClass('fa-info-circle');
  $dialog.find('.toast-header i').removeClass('text-danger text-success').addClass('text-success');
  _show_popup($dialog, title, text);
}

function form_get_jobs() {
  var jobs = [];
  var err = false;

  if (CURRENT_DISTRO['prefer']) {
    CURRENT_DISTRO['prefer'].split(' ').forEach(function(i) {
      jobs.push(['job', 'favor', 'name', i]);
    });
  }

  var locales = $('#solve_job_locales').val()
  if (locales) {
    locales.split(' ').forEach(function(i) {
      jobs.push(['namespace', 'namespace:language({})'.replace('{}', i), '@SYSTEM']);
    });
  }

  var filesystems = $('#solve_job_filesystems').val()
  if (filesystems) {
    filesystems.split(' ').forEach(function(i) {
      jobs.push(['namespace', 'namespace:filesystem({})'.replace('{}', i), '@SYSTEM']);
    });
  }


  $('#solveform .solve_job_group').each(function(i){
    var $elem = $(this);
    var jobtype = $elem.find('.solve_job_button').text();
    var name = $elem.find('.solve_job_text').val();
    if (name == '') {
      show_error_popup('Error', 'must specify package name');
      err = true;
    } else {
      jobs.push(['job', jobtype.toLowerCase(), 'name', name]);
    }
  });
  if (err) {
    return null;
  }
  return jobs;
}

function form_get_repos() {
  var repos = [];
  $('#repolist input').each(function(){
    if (this.checked) {
      repos.push(this['data-repo']);
    }
  });
  return repos;
}

function Solvable(sid, data) {
  this.id = sid
  this._data = data;
  this.name = this._data['NAME'];
  this.lookup = function(i) { return this._data[i]};
}

function dict2solvables(d) {
  var solvables = []
  Object.getOwnPropertyNames(d).forEach(function(sid) {
    solvables.push(new Solvable(sid, d[sid]))
  });
  return solvables;
}

function show_alternatives(relation) {

  $('#whatprovides_dialog_title').text("Providers for " + relation);
  $('#whatprovides_dialog_spinner').show();
  var $list = $('#whatprovides_dialog .list-group');
  $list.hide().empty();
  $('#whatprovides_dialog').modal('show');

  var ep_whatprovides = $('#ep_whatprovides').attr('url');
  $.getJSON(ep_whatprovides + '?' + $.param({'context': get_distro(), 'relation': relation, 'repo': form_get_repos()}), function(info, status) {
    var seen = {};
    $.each(info, function(i, d) {
      var solvable = dict2solvables(d)[0];
      $('<a href="#" class="list-group-item list-group-item-action"></a>').text(solvable.id).on("click", function(e){
	e.preventDefault();
	$('#whatprovides_dialog').modal('hide');
	add_new_job(solvable.name);
	solve();
      }).appendTo($list);
    });
    $('#whatprovides_dialog_spinner').hide();
    $list.show();
  });
}

function solve() {

  $('#solv_result').hide();
  $('#solv_result_packagelist').empty();
  var $table = $(`
    <table class="table table-striped table-hover">
      <thead>
        <tr>
          <th>Package</th>
          <th>Size</th>
          <th>Reason</th>
          <th>Rule</th>
        </tr>
      </thead>
      <tbody>
      </tbody>
    </table>`);

  var $tbody = $table.find('tbody');

  var data = 'system ' + get_arch() + ' rpm\n';

  form_get_repos().forEach(function(e, i){
    data += 'repo '+ e + "\n";
  });

  var jobs = form_get_jobs();
  if (!jobs) {
    return;
  }
  jobs.forEach(function(e, i){
    data += e.join(' ') + "\n";
  });

  if($('#solve_job_norecommends').is(':checked')) {
    data += 'solverflags ignorerecommended\n';
  }

  if($('#solve_job_addalreadyrecommended').is(':checked')) {
    data += 'solverflags addalreadyrecommended\n';
  }

  $('#solv_spinner').show();
  var ep_solve = $('#ep_solve').attr('url');
  ret = $.post(ep_solve + '?distribution=' + get_distro(), data, null, 'json' );
  ret.done(function(result, textStatus, xhr) {
    $('#solv_spinner').hide();
    var size = result['size'];
    $tbody.append(
      $("<tr></tr>")
        .append("<td>TOTAL</td>")
        // XXX: data-order via attr doesn't work with DataTable
        .append($(`<td data-order="${size}"></td>`).append(b2s(result['size'])))
        .append("<td></td>")
        .append("<td></td>")
    );
    var $buttons = $('#solv_choices_menu').empty();
    if (result.hasOwnProperty('choices') && result['choices'].length > 0) {
      $.each(result['choices'], function(i, c){
	$('<a class="dropdown-item" href="#"></a>').text(c).appendTo($buttons).on("click", function() {show_alternatives(c)});
      });
      $('#solv_choices').show();
    } else {
      $('#solv_choices').hide();
    }
    var $errorlist = $('#solv_problems');
    if (result.hasOwnProperty('problems')) {
      result['problems'].forEach(function(p) {
	$('<li class="list-group-item list-group-item-danger">').text(p).appendTo($errorlist);
      });
      $errorlist.show();
    } else {
      $errorlist.hide();
    }
    if (result.hasOwnProperty('newsolvables')) {
      result['newsolvables'].forEach(function(r) {
	// XXX: html quoting
	var $deps=$('<td></td>');
	r[2].forEach(function(rule){
	  var solvable = dict2solvables(rule[0])[0];
	  if (solvable.lookup('EVR').length) {
            $deps.append($('<a data-toggle="tooltip" data-placement="bottom" href="#"></a>')
              .attr('title', solvable.id)
              .text(solvable.name)
              .attr('href', '#package_'+solvable.name)
              );
	  } else {
	    $deps.append($('<span></span>').text(solvable.name));
	  }
	  var what = rule[1].toLowerCase();
	  if (what.substring(0, 4) == 'pkg_') {
	    what = what.substring(4);
	  }
	  $deps.append($('<span class="ml-1"></span>').text(what));
          if (rule[2].startsWith('(')) {
              $deps.append($('<i class="ml-2"></i>').text(rule[2]));
          } else {
            $deps.append(
              $('<a class="ml-1" data-toggle="tooltip" data-placement="bottom"></button>')
                .attr('title', rule[2])
                .text(rule[2])
                .attr('href', '#depinfo/'+rule[2])
                .on('click', dep_info_clicked)
            );
          }
          if (rule.length > 3 && rule[3]) {
            var s2 = dict2solvables(rule[3])[0];
            if (s2.lookup('EVR').length) {
              $deps.append($('<a data-toggle="tooltip" data-placement="bottom" class="ml-2"></button>')
                .attr('title', s2.id)
                .text(s2.name)
                .attr('href', '#package_'+s2.name)
              );
            } else {
              $deps.append($('<i class="ml-2"></i>').text(s2.name));
            }
          }
	  $deps.append($("<br>"));
	});
	var solvable = dict2solvables(r[0])[0];
	var name = solvable.name;
	var size = solvable.lookup('INSTALLSIZE');
	var reason = r[1];
	if (reason == 'UNIT_RULE') {
	  reason = ''; // most of them are UNIT_RULE and it's confusing
	}
	var $info_link = $('<a class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></a>')
          .attr('title', solvable.id)
          .text(name)
          .attr('href', '#info/'+name)
          .on('click', solvable_info_clicked);
	var $row = $("<tr id=\"package_"+name+'"></tr>');
	$('<td></td>').append($info_link).appendTo($row);
	$('<td></td>').attr('data-order', size).append(b2s(size)).appendTo($row);
	$('<td></td>').text(reason).appendTo($row);
	$row.append($deps);
        $tbody.append($row);
      });
      $('#solv_result_packagelist').append($table);
      $('#solv_result').show();
      var table = $table.DataTable({
        "scrollY": true,
        paging: false,
        "order": [[1, 'desc']],
        columnDefs: [
          { targets: [3], 'orderable': false },
          { targets: [1], 'searchable': false },
        ],
        "pageLength": 25
      });
    }
  });
  ret.fail(function(xhr, status, error) {
    $('#solv_spinner').hide();
    var $errorlist = $('#solv_problems');
    $('<li class="list-group-item list-group-item-danger">').text(JSON.parse(xhr.responseText)['message']).appendTo($errorlist);
    $errorlist.show();

  });
}

function solvable_info_clicked(e) {
  var name = e.target.getAttribute('title');
  show_solvable_info(name);
}

function show_solvable_info(name) {
  $('#solvable_info_spinner').show();
  $('#solvable_props').hide();
  $('#solvable_info_title').text(name);
  $('#solvable_info').modal('show');

  var ep_info = $('#ep_info').attr('url');

  //window.location.hash = '#info/' + name;

  var solvable2table =  function($body, props) {
      $.each(props, function(k,v){
	var $row = $('<tr></tr>');
	$('<td></td>').text(k).appendTo($row);
	var $col = $('<td></td>');
	if (Array.isArray(v)) {
	  var $list = $('<ul></ul>');
          if (k == 'REQUIRES' || k == 'PROVIDES' || k == 'SUGGESTS' ||  k == 'RECOMMENDS') {
            $.each(v, function(i, relation) {
            $('<li></li>').append(
              $('<a class="data-toggle="tooltip" data-placement="bottom"></button>')
                .attr('title', relation)
                .text(relation)
                .attr('href', '#depinfo/'+relation)
                .on('click', function(e) {
                  $('#solvable_info').one('hidden.bs.modal', function() { dep_info_clicked(e); });
                  $('#solvable_info').modal('hide');
                })).appendTo($list);
            });
          } else {
            $.each(v, function(i, line){$('<li><li>').text(line).appendTo($list)});
          }
	  $col.append($list);
	} else {
	  if (k == 'LICENSE') {
	    $col.append($('<a href="https://spdx.org/licenses/{}.html"></a>'.replace('{}', v)).text(v))
	  } else if (k.substr(-4) == 'SIZE') {
	    $col.append(b2s(v));
	  } else if (typeof(v) == 'string' && (v.substr(0, 7) == 'http://' || v.substr(0,8) == 'https://')) {
	    $('<a></a>').attr('href', v).text(v).appendTo($col);
	  } else {
	    $col.text(v)
	  }
	}
	$col.appendTo($row);
	$row.appendTo($body);
      });
    }


  $.getJSON(ep_info + '?' + $.param({'context': get_distro(), 'arch': get_arch(), 'package': name, 'repo': form_get_repos()}), function(info, status) {
    var $body = $('#solvable_props tbody');
    $body.empty();
    // XXX: we secrety take the first one
    var s = Object.getOwnPropertyNames(info)[0];
    $('#solvable_info_title').text(s);
    solvable2table($body, info[s])
    $('#solvable_info_spinner').hide();
    $('#solvable_props').show();
  });
}

function dep_info_clicked(e) {
  var name = e.target.getAttribute('title');
  show_dep_info(name);
}

function show_dep_info(name) {
  $('#dep_info_spinner').show();
  $('#dep_info_props').hide();
  $('#dep_info_title').text(name);
  $('#dep_info').modal('show');

  //window.location.hash = '#depinfo/' + name;

  var ep_depinfo = $('#ep_depinfo').attr('url');

  $.getJSON(ep_depinfo + '?' + $.param({'context': get_distro(), 'relation': name, 'repo': form_get_repos()}), function(info, status) {
    var $content = $('#dep_info_props');
    $content.empty();
    var relations = Object.getOwnPropertyNames(info);
    $.each(relations, function(i, r) {
      $content.append($('<h5></h5>').text(r));
      var $relationlist = $('<ul></ul>');
      $.each(info[r], function(i, sid) {
        $('<li></li>')
          .append(
            $('<a class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></a>')
            .attr('title', sid)
            .text(sid)
            .attr('href', '#info/'+sid)
            .on('click', function(e) {
              $('#dep_info').one('hidden.bs.modal', function() { solvable_info_clicked(e) });
              $('#dep_info').modal('hide');
            }))
        .appendTo($relationlist);
      });
      $content.append($relationlist);
    });
    $('#dep_info_spinner').hide();
    $('#dep_info_props').show();
  });
}


function search() {
  var form = document.getElementById('searchform');
  form.classList.add('was-validated');
  if (form.checkValidity() === false) {
    return;
  }

  var text = $('#search-text').val()
  if (!text) {
    return;
  }

  $('#search_result').empty().hide();
  var $table = $(`
    <table class="table table-striped table-hover">
      <thead>
        <tr>
          <th>Name</th>
          <th>Version</th>
          <th>Arch</th>
          <th>Repo</th>
          <th>Summary</th>
        </tr>
      </thead>
      <tbody>
      </tbody>
    </table>
  `);

  var $tbody = $table.find('tbody');

  $('#search_spinner').show();
  var ep_search = $('#ep_search').attr('url');
  var params = {'context': get_distro(), 'arch': get_arch(), 'text': text, 'repo': form_get_repos()};
  if ($('#search_provides').is(':checked')) {
    params['provides'] = 1;
  }
  $.getJSON(ep_search + '?' + $.param(params), function(info, status) {
    $.each(info, function(i, d) {
      var s = new Solvable(i, d);
      var $info_link = $('<a class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></a>')
        .attr('title', s.id)
        .text(s.name)
        .attr('href', '#info/'+s.id)
        .on('click', solvable_info_clicked);
      var $install_link = $('<button class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></button>')
        .attr('title', 'add to install set')
        .append($('<i class="fa fa-plus-square"></i>'))
        .on('click', function(e){
          e.preventDefault();
          // FIXME: we should actually fill the one where the search button was clicked
          var $input = $('#solveform .solve_job_text').last();
          if ($input.val())
            add_new_job(s.name);
          else
            $input.val(s.name);
          $("#solve-tab").tab('show');
        });
      var $row = $("<tr id=\"package_"+s.name+'"></tr>');
      $('<td></td>').append($info_link).append($install_link).appendTo($row);
      $('<td></td>').text(s.lookup('EVR')).appendTo($row);
      $('<td></td>').text(s.lookup('ARCH')).appendTo($row);
      $('<td></td>').text(s.lookup('repo')).appendTo($row);
      $('<td></td>').text(s.lookup('SUMMARY')).appendTo($row);
      $tbody.append($row);
    });
    $('#search_spinner').hide();
    $('#search_result').append($table).show();
    $table.DataTable({
      "order": [],
      "pageLength": 25
    });
  });

};

function b2s(size) {
  var i;
  var units = ['kB', 'MB', 'GB', 'TB'];
  for(i = -1; size > 1024 && i < units.length-1; ++i) {
      size = size / 1024;
  }
  if (i != -1)
    return Math.max(size, 0.1).toFixed(1) + "&nbsp;" + units[i];

  return size;
}

start();
});
