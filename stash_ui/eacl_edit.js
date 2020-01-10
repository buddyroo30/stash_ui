    //This was the starting point for this app:
    //https://www.phpcodify.com/add-remove-input-fields-dynamically-using-jquery-bootstrap/

    //Assumes the user has added content elements like this (below code works with this):
    //<div class="after-add-more-<NAME>">
    //  <div class="input-group-btn"> 
    //	  <button class="btn btn-primary add-more-<NAME>" type="button"><i class="glyphicon glyphicon-plus"></i> Add ACL</button>
    //	</div>
    //</div>


    var ugSearchUrl = simple_stash_service_url;

    function initEditAclOnReady (inputNames) {

	for (var i=0; i < inputNames.length; i++) {
	    var curInputName = inputNames[i];
	    //here first get the contents of the div with name class copy-fields and add it to after "after-add-more" div class.
	    $(".add-more-" + curInputName).click(genAddMoreFunc(curInputName));
	    //here it will remove the current value of the remove button which has been pressed
	    $("body").on("click",".remove-" + curInputName,genRemoveAclRowFunc(curInputName));

	    initAclEntry (null,curInputName);
	}

    }

    function genAddMoreFunc (curInputName) {

	var addMoreFunc = function() {
	    if (isBlank(curInputName)) { curInputName = ''; }
	    var html = newInputRowHtml(inputRowCt, null, curInputName);
	    $(".after-add-more-" + curInputName).after(html);
	    addAutocomplete (inputRowCt,curInputName);
	    inputRowCt++;
	}
	return(addMoreFunc);
    }

    function genRemoveAclRowFunc (curInputName) {

	var removeAclRowFunc = function() {
	    if (isBlank(curInputName)) { curInputName = ''; }
	    $(this).parents(".acl-entry-row-" + curInputName).remove();
	}

	return(removeAclRowFunc);
    }

    function initAclEntry (eaclHash,curInputName) {

       if (isBlank(curInputName)) { curInputName = ''; }

       $('.acl-entry-row-' + curInputName).remove();
       inputRowCt = 0;

       if (!eaclHash) { return; }

       var fs_or_web_arr = ['web','fs','base'];

       for (var fsw_i=0; fsw_i < fs_or_web_arr.length; fsw_i++) {
	  var fs_or_web = fs_or_web_arr[fsw_i];
          var eacl = eaclHash[fs_or_web];
	  if (isBlank(eacl)) { continue; }
          var aclArr = eacl.split(",");
          for (var i=0; i < aclArr.length; i++) {
	     var curRowId = inputRowCt++;
	     var newRowHtml = newInputRowHtml(curRowId,fs_or_web, curInputName);
	     $(".after-add-more-" + curInputName).after(newRowHtml);
	     addAutocomplete (curRowId, curInputName);
             var curAclTxt = aclArr[i];
             var aclParts = curAclTxt.split(':');
	     if (aclParts[0] == 'u') {
	        $('input:radio[name="type_' + curInputName + '_' + curRowId + '"][value="u"]').prop('checked', true);
	        $('input:radio[name="type_' + curInputName + '_' + curRowId + '"][value="g"]').prop('checked', false);
             } else if (aclParts[0] == 'g') {
	        $('input:radio[name="type_' + curInputName + '_'  + curRowId + '"][value="u"]').prop('checked', false);
	        $('input:radio[name="type_' + curInputName + '_'  + curRowId + '"][value="g"]').prop('checked', true);
             } else {
	        $('input:radio[name="type_' + curInputName + '_'  + curRowId + '"][value="u"]').prop('checked', false);
	        $('input:radio[name="type_' + curInputName + '_'  + curRowId + '"][value="g"]').prop('checked', false);
             }
	     $("#ug_name_" + curInputName + '_'  + curRowId).val(aclParts[1]);
	     var aclValsTxt = aclParts[2];
	     var individualAclValsArr = aclValsTxt.split("");
             for (var j=0; j < individualAclValsArr.length; j++) {
                var curVal = individualAclValsArr[j];
	        $("#acl_" + curVal + "_" + curInputName + "_" + curRowId).prop('checked',true);
             }

	     if (fs_or_web == 'base') {
		 $('input:radio[name="type_' + curInputName + '_' + curRowId + '"]').attr('disabled', true);
		 $('select[name="fs_or_web_' + curInputName + '_' + curRowId + '"]').attr('disabled', true);
		 $('#remove_' + curInputName + '_' + curRowId).attr('disabled', true);
		 if ((aclParts[0] == 'o') || (aclParts[0] == 'u')) { //can only change base group name
		     $("#ug_name_" + curInputName + '_'  + curRowId).attr('disabled', true);
		 }
		 if (aclParts[0] == 'o') {
		     $("#ug_name_" + curInputName + '_'  + curRowId).val('OTHER');
		 }
	     }
          }
       }
    }

    function SortByLabel(a, b){
       var aLabel = a.label.toLowerCase();
       var bLabel = b.label.toLowerCase(); 
       return ((aLabel < bLabel) ? -1 : ((aLabel > bLabel) ? 1 : 0));
    }

    function addAutocomplete (idx, curInputName) {

       var fsVal = '';
       if (queryParams['fs']) { fsVal = queryParams['fs'][0]; } //queryParams set in stash_ui.js

       $( "#ug_name_" + curInputName + '_' + idx).autocomplete({
          source: function( request, response ) {

	    var fs_or_web = $("select[name='fs_or_web_" + curInputName + '_' + idx + "'] option:selected").val();
	    var type = $("input[name='type_" + curInputName + '_' + idx + "']:checked").val();

	    if ((fs_or_web == 'web') && (type == 'u')) {
               $.ajax( {
                        url: "/cgi-bin/stash_ui_release/searchLdap_direct.cgi",
                        dataType: "jsonp",
		        jsonp: "callback",
                        data: {
                               search_text: request.term
                        },
                        success: function( data ) {
			                           var resultArr = jQuery.map( data.results, function( val, i ) {
			                                              return ( { 'label': val.userid_cn, 'value': val.userid } );
			                                           });
			                           resultArr.sort(SortByLabel);
                                                   response( resultArr );
                                                  }
                     } );
            } else if ((fs_or_web == 'web') && (type == 'g')) {
               $.ajax( {
                        url: ugSearchUrl,
                        dataType: "jsonp",
		        jsonp: "callback",
                        data: {
                               search_ug_search_text: request.term,
			       fs: fsVal,
			       search_ug_user_or_group: 'group',
			       search_ug_fs_or_web: 'web',
			       a: 'search_ug'
                        },
                        success: function( data ) {
                                                   response( data.results );
                                                  }
                     } );
            } else if (((fs_or_web == 'fs') || (fs_or_web == 'base')) && (type == 'u')) {
               $.ajax( {
                        url: ugSearchUrl,
                        dataType: "jsonp",
		        jsonp: "callback",
                        data: {
                               search_ug_search_text: request.term,
			       fs: fsVal,
			       search_ug_user_or_group: 'user',
			       search_ug_fs_or_web: 'fs',
			       a: 'search_ug'
                        },
                        success: function( data ) {
                                                   response( data.results );
                                                  }
                     } );
            } else if (((fs_or_web == 'fs') || (fs_or_web == 'base')) && (type == 'g')) {
               $.ajax( {
                        url: ugSearchUrl,
                        dataType: "jsonp",
		        jsonp: "callback",
                        data: {
                               search_ug_search_text: request.term,
			       fs: fsVal,
			       search_ug_user_or_group: 'group',
			       search_ug_fs_or_web: 'fs',
			       a: 'search_ug'
                        },
                        success: function( data ) {
                                                   response( data.results );
                                                  }
                     } );
            }
          },
	  autoFocus: true,
          minLength: 2,
          select: function( event, ui ) {
	     $(this).val(ui.item ? ui.item : " ");
          },
	  change: function (event, ui) {
             if (!ui.item) {
                this.value = '';
	     }
          }

       });

    }

    var oldSelIdxHash = {};

    function onTypeChange (selObj, i, curInputName) {
	var oldSelIdx = oldSelIdxHash['fs_or_web_' + curInputName + '_' + i];
	if (isBlank(oldSelIdx)) { oldSelIdx = 2; }
	var baseCt = 0;
	$('.' + curInputName).each(function(i, obj) {
	    if (obj.value == 'base') { baseCt++; }
	});
	if (baseCt > 3) {
	    alert("There can only be up to 3 entries of type 'Base'");
	    selObj.selectedIndex = oldSelIdx;
	} else {
	    oldSelIdxHash['fs_or_web_' + curInputName + '_' + i] = selObj.selectedIndex;
	    emptyTextBox(i,curInputName);
	}

	if (selObj.options[selObj.selectedIndex].value === 'web') {
	    $('#acl_w_' + curInputName + '_' + i).prop('checked',false);
	    $('#acl_x_' + curInputName + '_' + i).prop('checked',false);
	    $('#acl_w_' + curInputName + '_' + i).attr('disabled',true);
	    $('#acl_x_' + curInputName + '_' + i).attr('disabled',true);
	} else {
	    $('#acl_w_' + curInputName + '_' + i).attr('disabled',false);
	    $('#acl_x_' + curInputName + '_' + i).attr('disabled',false);
	}
    }

    function emptyTextBox (i, curInputName) {
	$("#ug_name_" + curInputName + "_" + i).val('');
    }

    function newInputRowHtml (i,type, curInputName) {

        //<!-- Copy Fields-These are the fields which we get through jquery and then add after the above input,-->
        var newRowTxt = "";
        newRowTxt += '  <form class="form-inline acl-entry-row-' + curInputName + '" style="margin-top:10px;">';
	if (type == 'fs') {
	   newRowTxt += '<select onchange="onTypeChange(this, ' + i + ',\'' + curInputName + '\');" style="margin-right:10px;" class=' + curInputName + ' name="fs_or_web_' + curInputName + '_' + i + '" ><option value=base>Base</option><option value=fs selected>Ext</option><option value=web>Web</option></select>';
	    oldSelIdxHash['fs_or_web_' + curInputName + '_' + i] = 1;
        } else if (type == 'web') {
	   newRowTxt += '<select onchange="onTypeChange(this, ' + i + ',\'' + curInputName + '\');" style="margin-right:10px;" class=' + curInputName + ' name="fs_or_web_' + curInputName + '_' + i + '" ><option value=base>Base</option><option value=fs>Ext</option><option value=web selected>Web</option></select>';
	    oldSelIdxHash['fs_or_web_' + curInputName + '_' + i] = 2;
        } else if (type == 'base') {
	   newRowTxt += '<select onchange="onTypeChange(this, ' + i + ',\'' + curInputName + '\');" style="margin-right:10px;" class=' + curInputName + ' name="fs_or_web_' + curInputName + '_' + i + '" ><option value=base selected>Base</option><option value=fs>Ext</option><option value=web>Web</option></select>';
	    oldSelIdxHash['fs_or_web_' + curInputName + '_' + i] = 0;
        } else {
	   newRowTxt += '<select onchange="onTypeChange(this, ' + i + ',\'' + curInputName + '\');" style="margin-right:10px;" class=' + curInputName + ' name="fs_or_web_' + curInputName + '_' + i + '" ><option value=base>Base</option><option value=fs selected>Ext</option><option value=web>Web</option></select>';
	    oldSelIdxHash['fs_or_web_' + curInputName + '_' + i] = 1;
        }
	newRowTxt += '    <label class="radio-inline"><input type="radio" onchange="emptyTextBox(' + i + ',\'' + curInputName + '\');" name="type_' + curInputName + '_' + i + '" value="u" checked>User</label>';
	newRowTxt += '    <label class="radio-inline"><input type="radio" onchange="emptyTextBox(' + i + ',\'' + curInputName + '\');" name="type_' + curInputName + '_' + i + '" value="g">Group</label>&nbsp;';
        newRowTxt += '    <input type="text" id="ug_name_' + curInputName + '_' + i + '" class="form-control" placeholder="Type Value Here...">';
	newRowTxt += '    <label class="checkbox-inline"><input id="acl_r_' + curInputName + '_' + i + '" type="checkbox" value="read">r</label>';
	var wxDisabledTxt = "";
	if (type === 'web') { wxDisabledTxt = " disabled"; }
	newRowTxt += '    <label class="checkbox-inline"><input id="acl_w_' + curInputName + '_' + i + '" type="checkbox" value="write"' + wxDisabledTxt + '>w</label>';
	newRowTxt += '    <label class="checkbox-inline"><input id="acl_x_' + curInputName + '_' + i + '" type="checkbox" value="execute"' + wxDisabledTxt + '>x</label>&nbsp;';
        newRowTxt += '    <button id="remove_' + curInputName + '_' + i + '" class="btn btn-xs btn-danger remove-' + curInputName + '" type="button"><i class="glyphicon glyphicon-remove"></i></button>';
        newRowTxt += '  </form>';

        return(newRowTxt);
    }

    function getAclVals (maxCt, curInputName) {

        var allBaseAcl = [];
        var allFsAcl = [];
        var allWebAcl = [];
        for (var i=0; i<maxCt; i++) {
           if ($("#ug_name_" + curInputName + '_' + i).length) { //Test for element existence, i.e. https://learn.jquery.com/using-jquery-core/faq/how-do-i-test-whether-an-element-exists/
	      var fs_or_web = $("select[name='fs_or_web_" + curInputName + '_' + i + "'] option:selected").val();
	      var type = $("input[name='type_" + curInputName + '_' + i + "']:checked").val();
	      if (isBlank(type)) { type = 'o'; }
	      var ug_name = $("#ug_name_" + curInputName + '_' + i).val();
	      var aclTxt = "";
	      if ($('#acl_r_' + curInputName + '_' + i).is(":checked")) { aclTxt += 'r'; }
	      if ($('#acl_w_' + curInputName + '_' + i).is(":checked")) { aclTxt += 'w'; }
	      if ($('#acl_x_' + curInputName + '_' + i).is(":checked")) { aclTxt += 'x'; }
	      if (isBlank(aclTxt)) { aclTxt = '-'; } //See here: https://unix.stackexchange.com/questions/209487/how-can-i-use-setfacl-to-give-no-access-to-other-users
	      if (!isBlank(ug_name)) {
	         var curAcl = type + ':' + ug_name + ':' + aclTxt;
		 if (fs_or_web == 'fs') {
                    allFsAcl.push(curAcl);
		 } else if (fs_or_web == 'web') {
                    allWebAcl.push(curAcl);
                 } else if (fs_or_web == 'base') {
                    allBaseAcl.push(curAcl);
		 }
	      } else {
		  return({ "err_msg": "Error: You must provide user/group names for all entries." });
	      }
	   }
	}
        return({ 'base': allBaseAcl, 'fs': allFsAcl, 'web': allWebAcl });
    }

    function isBlank(str) {
       return (!str || /^\s*$/.test(str));
    }
