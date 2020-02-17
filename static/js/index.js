$(document).ready(function() {
var $JOB_TEMPLATE;
var $REPO_TEMPLATE;

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

  $('#solv_result').hide();
  $('#solv_spinner').hide();
}

function add_new_job(name = null) {
  var $elem = $JOB_TEMPLATE.clone()
  if (name) {
    $elem.find('.solve_job_text').each(function() { this.value = name;});
  }
  $elem.insertBefore('#btn-add');
  job_setup_callbacks($elem);
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

    $('#btn-add').on('click', function() { add_new_job() });

    $('#btn-solve').on('click', function () { solve() });

    $('#btn-search').on('click', function() { search() })
    $('#search-text').on('keypress', function (e) {
      if (e.which == 13) {
        search();
      }
    });
  });
}

function show_error_popup(title, text) {
  var $dialog = $('.toast');
  $dialog.find('strong').text(title);
  $dialog.find('.toast-body').text(text);
  $dialog.toast('show');
}

function form_get_jobs() {
  var jobs = [];
  var err = false;
  $('#solveform .solve_job_group').each(function(i){
    var jobtype = '';
    var name = '';
    var $elem = $(this);
    $elem.find('.solve_job_button').each(function() { jobtype = this.textContent;});
    $elem.find('.solve_job_text').each(function() { name = this.value;});
    jobs.push(['job', jobtype.toLowerCase(), 'name', name]);
    if (name == '') {
      show_error_popup('Error', 'must specify package name');
      err = true;
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
  $.getJSON(ep_whatprovides + '?' + $.param({'context': get_distro(), 'relation': relation}), function(info, status) {
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

  $('#solv_spinner').show();
  var ep_solve = $('#ep_solve').attr('url');
  ret = $.post(ep_solve + '?distribution=' + get_distro(), data, null, 'json' );
  ret.done(function(result, textStatus, xhr) {
    $('#solv_spinner').hide();
    var $tbody = $('#solv_result tbody');
    $tbody.empty();
    $tbody.append("<tr><td>TOTAL</td><td>"+result['size']+"</td><td></td><td></td></tr>");
    if (result.hasOwnProperty('choices') && result['choices'].length > 0) {
      console.log("have choices");
      var $buttons = $('#solv_choices_menu').empty();
      $.each(result['choices'], function(i, c){
	$('<a class="dropdown-item" href="#"></a>').text(c).appendTo($buttons).on("click", function() {show_alternatives(c)});
      });
      $('#solv_choices').show();
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
	deps='';
	r[2].forEach(function(rule){
	  var solvable = dict2solvables(rule[0])[0];
	  var what = rule[1].toLowerCase();
	  if (what.substring(0, 4) == 'pkg_') {
	    what = what.substring(4);
	  }
	  if (what != 'supplemented') {
	    deps += '<a href="#package_' + solvable.name + '">' + solvable.name + '</a> ';
	  } else {
	    deps += '<span>' + solvable.name + '</span> ';
	  }
	  deps += what + ' ';
	  for (i=2; i< rule.length; ++i) {
	    deps += '<i>';
	    if(rule[i]) {
	      deps += ' ' + rule[i];
	    }
	    deps += '</i>';
	  }
	  deps += "<br>";
	});
	var solvable = dict2solvables(r[0])[0];
	var name = solvable.name;
	var size = solvable.lookup('INSTALLSIZE');
	var reason = r[1];
	if (reason == 'UNIT_RULE') {
	  reason = ''; // most of them are UNIT_RULE and it's confusing
	}
	var $info_link = $('<button class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></button>').attr('title', solvable.id).text(name).on('click', solvable_info_clicked);
	var $row = $("<tr id=\"package_"+name+'"></tr>');
	$tbody.append($row);
	$('<td></td>').append($info_link).appendTo($row);
	$('<td></td>').text(size).appendTo($row);
	$('<td></td>').text(reason).appendTo($row);
	$('<td></td>').append($(deps)).appendTo($row);
      });
      $('#solv_result').show();
    }
  });
  ret.fail(function(xhr, status, error) {
    $('#solv_spinner').hide();
    show_error_popup(error, JSON.parse(xhr.responseText)['message']);
  });
}

function solvable_info_clicked(e) {
  var name = e.target.getAttribute('title');
  $('#solvable_info_spinner').show();
  $('#solvable_props').hide();
  $('#solvable_info_title').text(name);
  $('#solvable_info').modal('show');

  var ep_info = $('#ep_info').attr('url');

  var solvable2table =  function($body, props) {
      $.each(props, function(k,v){
	var $row = $('<tr></tr>');
	$('<td></td>').text(k).appendTo($row);
	var $col = $('<td></td>');
	if (Array.isArray(v)) {
	  var $list = $('<ul></ul>');
	  $.each(v, function(i, line){$('<li><li>').text(line).appendTo($list)});
	  $col.append($list);
	} else {
	  if (k == 'LICENSE') {
	    $col.append($('<a href="https://spdx.org/licenses/{}.html"></a>'.replace('{}', v)).text(v))
	  } else if (k.substr(-4) == 'SIZE') {
	    $col.text(b2s(v));
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


  $.getJSON(ep_info + '?' + $.param({'context': get_distro(), 'arch': get_arch(), 'package': name}), function(info, status) {
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

function search() {
  $('#search_result').hide();
  $('#search_spinner').show();
  var ep_search = $('#ep_search').attr('url');
  var text = $('#search-text').val()
  if (!text) {
    show_error_popup("missing text");
    $('#search_spinner').hide();
    return;
  }
  $.getJSON(ep_search + '?' + $.param({'context': get_distro(), 'arch': get_arch(), 'text': text}), function(info, status) {
    var $tbody = $('#search_result tbody');
    $tbody.empty();
    $.each(info, function(i, d) {
      var s = new Solvable(i, d);
      var $info_link = $('<button class="btn btn-link" data-toggle="tooltip" data-placement="bottom"></button>').attr('title', s.id).text(s.name).on('click', solvable_info_clicked);
      var $row = $("<tr id=\"package_"+s.name+'"></tr>');
      $tbody.append($row);
      $('<td></td>').append($info_link).appendTo($row);
      $('<td></td>').text(s.lookup('EVR')).appendTo($row);
      $('<td></td>').text(s.lookup('ARCH')).appendTo($row);
      $('<td></td>').text(s.lookup('SUMMARY')).appendTo($row);
    });
    $('#search_spinner').hide();
    $('#search_result').show();
  });

};

function b2s(size) {
  var i;
  var units = [' kB', ' MB', ' GB', ' TB'];
  for(i = -1; size > 1024 && i < units.length-1; ++i) {
      size = size / 1024;
  }

  return Math.max(size, 0.1).toFixed(1) + units[i];
}

start();
});
