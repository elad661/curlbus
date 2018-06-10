"""HTML template for curlbus + ansi2html """

html_template = """<!DOCTYPE HTML>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<link href='https://fonts.googleapis.com/css?family=Alef' rel='stylesheet' type='text/css'>
<link rel="stylesheet" type="text/css" href="/static/style.css">
<title>%(title)s</title>
<!-- The CSS/HTML ahead is not great, but you should be using curl anyway, not a browser !-->
<style type="text/css">
%(style)s
</style>
</head>
<body>
<div id="terminal"><!-- ansi2html is still here for supporting browsers with no JS --!>
    <input id="in" autocomplete="off" autocorrect="off">
    <div id="display">
        <pre class="ansi2html-content">
%(content)s</pre><div></div>
    </div>
    <div id="inputline"><span class="terminput"><span class="prompt">guest@curlbus:/$ </span><span><span></span><span id="caret" class="blink">&nbsp;</span>&nbsp;</span><span></span></span><span id="spinner"></span></div>
</div>
<div></div>
<svg width="16" height="12">
  <rect width="100%%" height="50%%" fill="#d70270"></rect>
  <rect width="100%%" y="50%%" height="50%%" fill="#0038a8"></rect>
  <rect width="100%%" y="40%%" height="20%%" fill="#734f96"></rect>
</svg>
<footer>
<span class="curlmsg">
Best viewed using curl! try <pre>curl https://curlbus.app</pre>
</span>
<div>
Created by <a href="https://eladalfassa.com">Elad Alfassa</a>.
</div>
</footer>
    <script type="text/javascript" src="/static/jquery-3.3.1.min.js" defer></script>
    <script type="text/javascript" src="/static/cli.js" defer></script>
    <script type="text/javascript" src="/static/ansi_up.js" defer></script>
</body>
</html>
"""