"use strict"
/*
 Terminal emulation for curlbus web
 Based on unixckd - https://github.com/chromakode/xkcdfools
 Rewritten for curlbus by Ari Zellner and Elad Alfassa, 2018
*/

/*
 Client-side logic for Wordpress CLI theme
 R. McFarland, 2006, 2007, 2008
 http://thrind.xamai.ca/
 
 jQuery rewrite and overhaul
 Chromakode, 2010
 http://www.chromakode.com/
*/

var TerminalShell = {
    commands: {
        clear: function(terminal) {
            terminal.clear();
        },
        reset: function(terminal) {
            window.location.reload();
        }
    },
    filters: [],
    fallback: null,

    lastCommand: null,
    process: function(terminal, cmd) {
        try {
            terminal.setWorking(true);
            if (this.commands[cmd] === undefined) {
                // Seriously? we need regex just to replace all spaces? WTF!
                cmd = cmd.replace(new RegExp(" ", 'g'), "/");
                var server = window.location.protocol + "//" + window.location.host + '/';

                terminal.print('curl ' + server + cmd);
                fetch(server + cmd,
                {
                    headers: {'Accept': 'text/plain'    },
                }).then(function(response) {
                    return response.text();
                }).then(function(text) {
                    var ansi_up = new AnsiUp;
                    var html = ansi_up.ansi_to_html(text);
                    html = ansi_up.old_linkify(html);
                    // linkify relative links:
                    html = html.replace(new RegExp("(│|\\s|^)((?:\/\\w+)+)", 'gu'), '$1<a href="$2" class="curlbusrelative">$2</a>')

                    $('.curlmsg').fadeOut("fast");
                    terminal.print($('<pre>').html(html));
                    terminal.setWorking(false);
                    terminal.setCursorState(true);
                    window.scrollTo(0, document.body.scrollHeight);
                });
            } else {
                this.commands[cmd](terminal);
                terminal.setWorking(false);
            }

            this.lastCommand = cmd;
        } catch (e) {
            terminal.print($('<p>').addClass('error').text('An internal error occured: '+e));
            terminal.setWorking(false);
        }
    }
};

var Terminal = {
    buffer: '',
    pos: 0,
    history: [],
    historyPos: 0,
    promptActive: true,
    _cursorBlinkTimeout: null,
    _keyDownTimeout: null,
    spinnerIndex: 0,
    _spinnerTimeout: null,

    output: TerminalShell,

    config: {
        scrollStep:            20,
        scrollSpeed:        100,
        bg_color:            '#000',
        fg_color:            '#FFF',
        prompt:                'guest@curlbus:/$ ',
        spinnerCharacters:    ['[   ]','[.  ]','[.. ]','[...]'],
        spinnerSpeed:        250,
        typingSpeed:        50
    },

    init: function() {
        document.getElementById("terminal").addEventListener("click", function() {
            var input = document.getElementById("in");
            if (document.activeElement != input && String(window.getSelection()) == "") {
              input.focus();
            }
        });
        var input = document.getElementById("in");
        input.value = ""; // browsers might pre-fill values on reload
        input.addEventListener("input", function(e) {
            Terminal.updateInputDisplay();
        });
        document.addEventListener("keypress", function(e) {
            var input = document.getElementById("in");
            if (document.activeElement != input && !e.ctrlKey && !e.metaKey) {
                if (e.key == "ArrowLeft" ||
                    e.key == "ArrowRight" ||
                    e.key == "ArrowUp" ||
                    e.key == "ArrowDown" ||
                    e.key == "Home" ||
                    e.key == "End") {
                  input.focus();
                }
                if (e.which >= 32 && e.which <= 126) {
                  input.value += e.key;
                  Terminal.updateInputDisplay();
                  input.focus();
                }
            }
        });
        input.addEventListener("keydown", function(e) {
            var caret = document.getElementById("caret");
            if (this._keyDownTimeout !== null) {
                window.clearTimeout(this._keyDownTimeout);
            }
            if (e.key == "ArrowUp") {
                  e.preventDefault();
                  Terminal.moveHistory(-1);
              } else if (e.key == "ArrowDown") {
                  e.preventDefault();
                  Terminal.moveHistory(1);
              }
            this._keyDownTimeout = window.setTimeout(function() {
                var input = document.getElementById("in");
                if (e.key == "ArrowLeft" ||
                    e.key == "ArrowRight" ||
                    e.key == "Home" ||
                    e.key == "End") {
                    Terminal.updateInputDisplay();
                } else if (e.key == "Enter") {
                    if (Terminal.promptActive) {
                      Terminal.processInputBuffer();
                      Terminal.setCursorState(true);
                    }
                }
                this._keyDownTimeout = null;
            }, 15); // Delay by 15ms to let the browser update the input
        });

        $(window).resize(function(e) { $('#terminal').scrollTop($('#terminal').attr('scrollHeight')); });

        this.setCursorState(true);
        this.setWorking(false);
        $('#prompt').html(this.config.prompt);
        $('#inputline').fadeIn('fast').addClass("withjs");
        $('#terminal').hide().fadeIn('fast');

        if (localStorage.getItem("history") !== null) {
            this.history = JSON.parse(localStorage.getItem('history'));
            this.historyPos = this.history.length;
        }
    },

    setCursorState: function(state) {
      if (this._cursorBlinkTimeout !== null) {
        window.clearTimeout(this._cursorBlinkTimeout);
        this._cursorBlinkTimeout = null;
      }
      document.getElementById("caret").classList.remove('blink')
      if (state) {
        this._cursorBlinkTimeout = window.setTimeout(function() {
          document.getElementById("caret").classList.add('blink')
          this._cursorBlinkTimeout = null;
        }, 500);
      }
    },

    updateInputDisplay: function() {
        this.setCursorState(false);
        var input = document.getElementById("in");
        var before_caret = input.value.slice(0, input.selectionStart);
        var after_caret = input.value.slice(input.selectionEnd + 1);
        var in_caret = input.value.slice(input.selectionStart, input.selectionEnd + 1);
        caret.previousSibling.textContent = before_caret;
        caret.nextSibling.textContent = after_caret;
        caret.innerHTML = in_caret || '&nbsp;';
        this.jumpToBottom();
        this.setCursorState(true);
        return;
    },

    clearInputBuffer: function() {
        var caret = document.getElementById("caret");
        document.getElementById("in").value = "";
        caret.previousSibling.textContent = "";
        caret.nextSibling.textContent = "";
        caret.innerHTML = "&nbsp;";
        this.updateInputDisplay();
    },

    clear: function() {
        $('#display').html('');
    },

    moveHistory: function(val) {
        this.setCursorState(false);
        var newpos = this.historyPos + val;
        if ((newpos >= 0) && (newpos <= this.history.length)) {
            if (newpos == this.history.length) {
                this.clearInputBuffer();
            } else {
                document.getElementById("in").value = this.history[newpos];
            }
            this.historyPos = newpos;
            this.updateInputDisplay();
            this.jumpToBottom();
        }
        this.setCursorState(true);
    },

    addHistory: function(cmd) {
        this.historyPos = this.history.push(cmd);
        localStorage.setItem('history', JSON.stringify(this.history))
    },

    jumpToBottom: function() {
       window.scrollTo(0, document.body.scrollHeight);
    },

    print: function(text) {
        if (!text) {
            $('#display').append($('<div>'));
        } else if( text instanceof jQuery ) {
            $('#display').append(text);
        } else {
            var av = Array.prototype.slice.call(arguments, 0);
            $('#display').append($('<p>').text(av.join(' ')));
        }
        this.jumpToBottom();
        window.scrollTo(0, document.body.scrollHeight);
    },

    processInputBuffer: function(cmd) {
        var buffer = document.getElementById("in").value;
        this.print($('<p>').addClass('command').text(this.config.prompt + buffer));
        var cmd = buffer;
        this.clearInputBuffer();
        if (cmd.length == 0) {
            return false;
        }
        this.addHistory(cmd);
        if (this.output) {
            return this.output.process(this, cmd);
        } else {
            return false;
        }
    },

    setPromptActive: function(active) {
        this.promptActive = active;
        $('.terminput').toggle(this.promptActive);
    },

    setWorking: function(working) {
        if (working && !this._spinnerTimeout) {
            $('#display .command:last-child').add('#bottomline').first().append($('#spinner'));
            this._spinnerTimeout = window.setInterval($.proxy(function() {
                if (!$('#spinner').is(':visible')) {
                    $('#spinner').fadeIn().css("display", "inline-block");
                }
                this.spinnerIndex = (this.spinnerIndex + 1) % this.config.spinnerCharacters.length;
                $('#spinner').text(this.config.spinnerCharacters[this.spinnerIndex]);
            },this), this.config.spinnerSpeed);
            this.setPromptActive(false);
            this.jumpToBottom();
        } else if (!working && this._spinnerTimeout) {
            clearInterval(this._spinnerTimeout);
            this._spinnerTimeout = null;
            $('#spinner').fadeOut();
            this.setPromptActive(true);
        }
    },

    runCommand: function(text) {
        var index = 0;
        var mine = false;

        this.promptActive = false;
        var interval = window.setInterval($.proxy(function typeCharacter() {
            if (index < text.length) {
                this.addCharacter(text.charAt(index));
                index += 1;
            } else {
                clearInterval(interval);
                this.promptActive = true;
                this.processInputBuffer();
            }
        }, this), this.config.typingSpeed);
    }
};

$(document).ready(function() {
    if (window.fetch != undefined)  // Guard against IE11
      Terminal.init();
});