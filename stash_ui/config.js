
const simple_stash_service_url = '/cgi-bin/stash_ui_release/simple_stash.cgi'; //Change to url where the simple_stash.cgi service is installed/running

const smErrCheckTxt = "smusath.net.bms.com/siteminderagent/forms/authform.fcc"; //For use with SiteMinder, to check cookie timeout

const localStorageName = 'settings'; //user credentials (password, private SSH key) will be stored in browser local storage under this name

const ALLOW_RENAME_DELETE = false; //Set to true to allow the 'Delete' and 'Rename' context menu items to be shown and used

//See here for info about Font Awesome fonts I'm using: https://www.w3schools.com/icons/fontawesome_icons_filetype.asp
var fileTypeIconClasses =
{ 'pdf': 'fa fa-file-pdf-o',
  'doc': 'fa fa-file-word-o',
  'docx': 'fa fa-file-word-o',
  'xls': 'fa fa-file-excel-o',
  'xlsx': 'fa fa-file-excel-o',
  'ppt': 'fa fa-file-powerpoint-o',
  'pptx': 'fa fa-file-powerpoint-o',
  'txt': 'fa fa-file-text-o',
  'pl': 'fa fa-file-code-o',
  'py': 'fa fa-file-code-o',
  'r': 'fa fa-file-code-o',
  'java': 'fa fa-file-code-o',
  'js': 'fa fa-file-code-o',
  'png': 'fa fa-file-image-o',
  'gif': 'fa fa-file-image-o',
  'jpg': 'fa fa-file-image-o',
  'jpeg': 'fa fa-file-image-o' };
