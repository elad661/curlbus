"""HTML template for curlbus + ansi2html """

html_template = """<!DOCTYPE HTML>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href='https://fonts.googleapis.com/css?family=Alef' rel='stylesheet' type='text/css'>
<title>%(title)s</title>
<!-- The CSS/HTML ahead is not great, but you should be using curl anyway, not a browser !-->
<style type="text/css">
    body, html {
    width: 100%%;
    padding: 0;
    margin: 0;
}
svg {
    position: fixed;
    right: 1px;
    bottom: 1px;
}
%(style)s
footer {
    font-family: 'Alef', 'helvetica', sans-serif;
}
footer pre {
    display: inline-block;
}
footer a, footer a:visited {
    color: white;
}
footer div {
    text-align: center;
    font-size: small;
    color: gray;
    position: fixed;
    width: 100%%;
    bottom: 0;
}
</style>
</head>
<body class="body_foreground body_background" style="font-size: %(font_size)s;" >
<pre class="ansi2html-content">
%(content)s
</pre>
<svg width="16" height="12">
  <rect width="100%%" height="50%%" fill="#d70270"></rect>
  <rect width="100%%" y="50%%" height="50%%" fill="#0038a8"></rect>
  <rect width="100%%" y="40%%" height="20%%" fill="#734f96"></rect>
</svg>
<footer>
Best viewed using curl! try <pre>curl https://curlbus.app</pre>
<div>
Made by <a href="https://eladalfassa.com">Elad Alfassa</a>.
</div>
</footer>
</body>
</html>
"""