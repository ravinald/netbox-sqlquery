(function () {
  function init() {
  var editor = document.getElementById("sql-editor");
  if (!editor) return;
  var form = editor.closest("form");
  var modeInput = document.getElementById("mode-input");
  var highlightPre = document.getElementById("sql-highlight");
  var highlightCode = highlightPre ? highlightPre.querySelector("code") : null;
  var wrapper = document.getElementById("sql-editor-wrapper");

  // Load schemas
  var rawSchema = {};
  var abstractSchema = {};
  try { rawSchema = JSON.parse(document.getElementById("schema-json").textContent); } catch (e) {}
  try { abstractSchema = JSON.parse(document.getElementById("abstract-schema-json").textContent); } catch (e) {}

  // Load highlight preferences
  var hlPrefs = { enabled: true, keyword: "2196f3", "function": "9c27b0", string: "2f6a31", number: "ff5722", operator: "aa1409", comment: "9e9e9e" };
  try {
    var loaded = JSON.parse(document.getElementById("highlight-prefs").textContent);
    for (var k in loaded) hlPrefs[k] = loaded[k];
  } catch (e) {}

  // Load flags (superuser, write confirm skip)
  var sqlFlags = { is_superuser: false, skip_write_confirm: false };
  try {
    var f = JSON.parse(document.getElementById("sqlquery-flags").textContent);
    for (var k in f) sqlFlags[k] = f[k];
  } catch (e) {}

  // Highlight enabled state (user pref + local toggle)
  var highlightOn = hlPrefs.enabled;
  var localToggle = localStorage.getItem("sqlquery_highlight");
  if (localToggle !== null) highlightOn = localToggle === "on";
  if (wrapper) wrapper.classList.toggle("highlight-off", !highlightOn);

  // SQL keywords and functions
  var SQL_KEYWORDS = new Set([
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
    "CROSS", "FULL", "ON", "AND", "OR", "NOT", "IN", "IS", "NULL", "AS",
    "DISTINCT", "GROUP", "BY", "ORDER", "LIMIT", "OFFSET", "HAVING",
    "BETWEEN", "LIKE", "ILIKE", "UNION", "ALL", "EXISTS", "CASE", "WHEN",
    "THEN", "ELSE", "END", "WITH", "SET", "INTO", "INSERT", "UPDATE",
    "DELETE", "CREATE", "DROP", "ALTER", "TABLE", "VIEW", "INDEX", "TRUE",
    "FALSE", "ASC", "DESC", "CAST", "NULLIF", "EXTRACT", "INTERVAL",
    "LOCAL", "TRANSACTION", "READ", "ONLY", "FILTER"
  ]);

  var SQL_FUNCTIONS = new Set([
    "COUNT", "SUM", "AVG", "MIN", "MAX", "STRING_AGG", "ARRAY_AGG",
    "COALESCE", "CONCAT", "UPPER", "LOWER", "TRIM", "SUBSTRING",
    "LENGTH", "NOW", "CURRENT_DATE", "CURRENT_TIMESTAMP", "REPLACE",
    "POSITION", "OVERLAY", "GREATEST", "LEAST", "ROUND", "CEIL",
    "FLOOR", "ABS", "MOD", "POWER", "SQRT", "DATE_TRUNC", "AGE",
    "TO_CHAR", "TO_DATE", "TO_NUMBER", "TO_TIMESTAMP", "REGEXP_REPLACE",
    "REGEXP_MATCHES", "GENERATE_SERIES", "UNNEST", "ROW_NUMBER",
    "RANK", "DENSE_RANK", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "NTILE", "OVER", "PARTITION"
  ]);

  var ALL_SQL_WORDS = new Set([...SQL_KEYWORDS, ...SQL_FUNCTIONS]);

  // --- Tokenizer ---
  function tokenize(sql) {
    var tokens = [];
    var i = 0;
    var len = sql.length;

    while (i < len) {
      // Single-line comment
      if (sql[i] === "-" && sql[i + 1] === "-") {
        var end = sql.indexOf("\n", i);
        if (end === -1) end = len;
        tokens.push({ type: "comment", value: sql.substring(i, end) });
        i = end;
        continue;
      }

      // String literal (single quotes)
      if (sql[i] === "'") {
        var j = i + 1;
        while (j < len) {
          if (sql[j] === "'" && sql[j + 1] === "'") { j += 2; continue; }
          if (sql[j] === "'") { j++; break; }
          j++;
        }
        tokens.push({ type: "string", value: sql.substring(i, j) });
        i = j;
        continue;
      }

      // Numbers
      if (/[0-9]/.test(sql[i]) && (i === 0 || /[\s,=(]/.test(sql[i - 1]))) {
        var j = i;
        while (j < len && /[0-9.]/.test(sql[j])) j++;
        tokens.push({ type: "number", value: sql.substring(i, j) });
        i = j;
        continue;
      }

      // Words (identifiers, keywords, functions)
      if (/[a-zA-Z_]/.test(sql[i])) {
        var j = i;
        while (j < len && /[a-zA-Z0-9_]/.test(sql[j])) j++;
        var word = sql.substring(i, j);
        var upper = word.toUpperCase();
        if (SQL_KEYWORDS.has(upper)) {
          tokens.push({ type: "keyword", value: word });
        } else if (SQL_FUNCTIONS.has(upper)) {
          tokens.push({ type: "function", value: word });
        } else {
          tokens.push({ type: "plain", value: word });
        }
        i = j;
        continue;
      }

      // Operators
      if ("<>=!".indexOf(sql[i]) !== -1) {
        var j = i;
        while (j < len && "<>=!".indexOf(sql[j]) !== -1) j++;
        tokens.push({ type: "operator", value: sql.substring(i, j) });
        i = j;
        continue;
      }

      // Everything else (whitespace, punctuation)
      tokens.push({ type: "plain", value: sql[i] });
      i++;
    }
    return tokens;
  }

  // --- HTML escape ---
  function escapeHTML(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // --- Highlight ---
  function highlightSQL(sql) {
    var tokens = tokenize(sql);
    var html = "";
    for (var t = 0; t < tokens.length; t++) {
      var tok = tokens[t];
      var escaped = escapeHTML(tok.value);
      var color = hlPrefs[tok.type];
      if (color && tok.type !== "plain") {
        html += '<span style="color:#' + color + '">' + escaped + "</span>";
      } else {
        html += escaped;
      }
    }
    return html;
  }

  // --- Sync highlight overlay with textarea ---
  function syncHighlight() {
    if (!highlightCode) return;
    highlightCode.innerHTML = highlightSQL(editor.value) + "\n";
    // Sync scroll position
    if (highlightPre) {
      highlightPre.scrollTop = editor.scrollTop;
      highlightPre.scrollLeft = editor.scrollLeft;
    }
  }

  // --- Auto-uppercase SQL keywords ---
  function autoUppercase() {
    var pos = editor.selectionStart;
    var val = editor.value;

    // Look backward from cursor for a word boundary
    if (pos === 0) return;
    var charBefore = val[pos - 1];
    // Only trigger after space, newline, tab, or paren
    if (" \n\t(".indexOf(charBefore) === -1) return;

    // Find the word before the trigger character
    var wordEnd = pos - 1;
    var wordStart = wordEnd;
    while (wordStart > 0 && /[a-zA-Z_]/.test(val[wordStart - 1])) wordStart--;

    if (wordStart === wordEnd) return;
    var word = val.substring(wordStart, wordEnd);
    var upper = word.toUpperCase();

    if (ALL_SQL_WORDS.has(upper) && word !== upper) {
      editor.value = val.substring(0, wordStart) + upper + val.substring(wordEnd);
      editor.selectionStart = editor.selectionEnd = pos;
    }
  }

  // Bind editor events
  editor.addEventListener("input", function () {
    autoUppercase();
    syncHighlight();
  });
  editor.addEventListener("scroll", function () {
    if (highlightPre) {
      highlightPre.scrollTop = editor.scrollTop;
      highlightPre.scrollLeft = editor.scrollLeft;
    }
  });

  // Sync dimensions on textarea resize
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(function () { syncHighlight(); }).observe(editor);
  }

  // Initial highlight
  syncHighlight();

  // Highlight toggle button
  var hlToggle = document.getElementById("highlight-toggle");
  if (hlToggle) {
    // Set initial visual state
    if (highlightOn) {
      hlToggle.classList.remove("btn-outline-secondary");
      hlToggle.classList.add("btn-secondary");
    }
    hlToggle.addEventListener("click", function () {
      highlightOn = !highlightOn;
      localStorage.setItem("sqlquery_highlight", highlightOn ? "on" : "off");
      if (wrapper) wrapper.classList.toggle("highlight-off", !highlightOn);
      hlToggle.classList.toggle("btn-secondary", highlightOn);
      hlToggle.classList.toggle("btn-outline-secondary", !highlightOn);
      if (highlightOn) syncHighlight();
    });
  }

  // --- Schema search filter ---
  var schemaFilter = document.getElementById("schema-filter");
  if (schemaFilter) {
    schemaFilter.addEventListener("input", function () {
      var query = schemaFilter.value.toLowerCase().trim();
      document.querySelectorAll(".schema-entry").forEach(function (entry) {
        if (!query) {
          entry.classList.remove("schema-hidden");
          entry.removeAttribute("open");
          return;
        }
        var tableName = (entry.dataset.table || "").toLowerCase();
        var columns = (entry.dataset.columns || "").toLowerCase();
        var match = tableName.indexOf(query) !== -1 || columns.indexOf(query) !== -1;
        entry.classList.toggle("schema-hidden", !match);
        if (match && columns.indexOf(query) !== -1) {
          entry.setAttribute("open", "");
        }
      });
    });
  }

  // --- Mode toggle ---
  document.querySelectorAll(".mode-toggle .btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = btn.dataset.mode;
      modeInput.value = mode;
      localStorage.setItem("sqlquery_mode", mode);
      document.querySelectorAll(".mode-toggle .btn").forEach(function (b) {
        b.classList.remove("btn-primary");
        b.classList.add("btn-outline-primary");
      });
      btn.classList.remove("btn-outline-primary");
      btn.classList.add("btn-primary");
      document.getElementById("schema-raw").style.display = mode === "raw" ? "" : "none";
      document.getElementById("schema-abstract").style.display = mode === "abstract" ? "" : "none";
    });
  });

  var savedMode = localStorage.getItem("sqlquery_mode");
  if (savedMode && savedMode !== modeInput.value) {
    var btn = document.querySelector('.mode-toggle .btn[data-mode="' + savedMode + '"]');
    if (btn) btn.click();
  }

  // --- Write query confirmation ---
  var WRITE_PREFIXES = ["INSERT", "UPDATE", "DELETE"];
  var confirmedInput = document.getElementById("confirmed-input");

  function isWriteQuery(sql) {
    var upper = sql.trimStart().toUpperCase();
    for (var i = 0; i < WRITE_PREFIXES.length; i++) {
      if (upper.indexOf(WRITE_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  function submitForm() {
    // For write queries by superuser: check if confirmation is needed
    if (sqlFlags.is_superuser && isWriteQuery(editor.value)) {
      if (sqlFlags.skip_write_confirm) {
        confirmedInput.value = "1";
        form.submit();
      } else {
        // Submit without confirmed flag -- server will return needs_confirm
        confirmedInput.value = "";
        form.submit();
      }
    } else {
      confirmedInput.value = "";
      form.submit();
    }
  }

  // Handle the confirmation modal buttons
  var confirmBtn = document.getElementById("write-confirm-btn");
  var cancelBtn = document.getElementById("write-cancel-btn");
  var confirmModal = document.getElementById("write-confirm-modal");

  if (confirmBtn) {
    confirmBtn.addEventListener("click", function () {
      // Check if "don't ask again" is checked
      var skipCheckbox = document.getElementById("skip-future-confirm");
      if (skipCheckbox && skipCheckbox.checked) {
        // Save preference via API
        fetch("/api/users/config/", {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
          },
          body: JSON.stringify({
            "plugins.netbox_sqlquery.skip_write_confirm": "on"
          }),
        });
      }
      confirmedInput.value = "1";
      form.submit();
    });
  }
  if (cancelBtn) {
    cancelBtn.addEventListener("click", function () {
      if (confirmModal) confirmModal.style.display = "none";
    });
  }

  // Run query button
  var runBtn = document.getElementById("run-query-btn");
  if (runBtn) {
    runBtn.addEventListener("click", function () { submitForm(); });
  }

  // Clear editor button
  var clearBtn = document.getElementById("clear-editor-btn");
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      editor.value = "";
      editor.focus();
      syncHighlight();
    });
  }

  // --- Save query dialog ---
  var saveModal = document.getElementById("save-query-modal");
  var saveBtn = document.getElementById("save-query-btn");
  var saveConfirmBtn = document.getElementById("save-query-confirm");

  function showModal(modal) {
    modal.style.display = "block";
    modal.classList.add("show");
    modal.style.background = "rgba(0,0,0,0.5)";
  }
  function hideModal(modal) {
    modal.style.display = "none";
    modal.classList.remove("show");
  }

  // Close buttons for modals
  document.querySelectorAll('[data-action="close-save"]').forEach(function (el) {
    el.addEventListener("click", function () { hideModal(saveModal); });
  });
  document.querySelectorAll('[data-action="close-load"]').forEach(function (el) {
    el.addEventListener("click", function () { hideModal(document.getElementById("load-query-modal")); });
  });

  if (saveBtn && saveModal) {
    saveBtn.addEventListener("click", function () {
      document.getElementById("save-query-error").style.display = "none";
      document.getElementById("save-query-success").style.display = "none";
      document.getElementById("save-query-name").value = "";
      document.getElementById("save-query-desc").value = "";
      showModal(saveModal);
      document.getElementById("save-query-name").focus();
    });
  }

  if (saveConfirmBtn) {
    saveConfirmBtn.addEventListener("click", function () {
      var name = document.getElementById("save-query-name").value.trim();
      var desc = document.getElementById("save-query-desc").value.trim();
      var vis = document.getElementById("save-query-visibility").value;
      var sql = editor.value.trim();
      var errEl = document.getElementById("save-query-error");
      var okEl = document.getElementById("save-query-success");

      errEl.style.display = "none";
      okEl.style.display = "none";

      if (!name || !sql) {
        errEl.textContent = "Name and SQL are required.";
        errEl.style.display = "block";
        return;
      }

      if (!/^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]*$/.test(name)) {
        errEl.textContent = "Name must start with a letter or number and contain only letters, numbers, spaces, hyphens, underscores, and periods.";
        errEl.style.display = "block";
        return;
      }

      fetch("/plugins/sqlquery/ajax/save-query/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify({ name: name, description: desc, visibility: vis, sql: sql }),
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          errEl.textContent = data.error;
          errEl.style.display = "block";
        } else {
          okEl.textContent = data.message;
          okEl.style.display = "block";
          setTimeout(function () { hideModal(saveModal); }, 1200);
        }
      })
      .catch(function () {
        errEl.textContent = "Failed to save query.";
        errEl.style.display = "block";
      });
    });
  }

  // --- Load query dialog ---
  var loadModal = document.getElementById("load-query-modal");
  var loadBtn = document.getElementById("load-query-btn");
  var loadSearch = document.getElementById("load-query-search");
  var loadList = document.getElementById("load-query-list");

  function fetchQueries(search) {
    var url = "/plugins/sqlquery/ajax/list-queries/";
    if (search) url += "?q=" + encodeURIComponent(search);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.results || data.results.length === 0) {
          loadList.innerHTML = '<div class="text-muted text-center py-3">No saved queries found.</div>';
          return;
        }
        var html = '<div class="list-group">';
        data.results.forEach(function (q) {
          html += '<a href="#" class="list-group-item list-group-item-action load-query-item" data-sql="' +
            q.sql.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") + '">' +
            '<div class="d-flex justify-content-between">' +
            '<strong>' + escapeHTMLText(q.name) + '</strong>' +
            '<small class="text-muted">' + escapeHTMLText(q.visibility) + ' &middot; ' + escapeHTMLText(q.owner) + '</small>' +
            '</div>' +
            (q.description ? '<small class="text-muted">' + escapeHTMLText(q.description) + '</small>' : '') +
            '</a>';
        });
        html += '</div>';
        loadList.innerHTML = html;

        // Bind click handlers
        loadList.querySelectorAll(".load-query-item").forEach(function (el) {
          el.addEventListener("click", function (e) {
            e.preventDefault();
            editor.value = el.dataset.sql;
            editor.focus();
            syncHighlight();
            hideModal(loadModal);
          });
        });
      })
      .catch(function () {
        loadList.innerHTML = '<div class="text-danger text-center py-3">Failed to load queries.</div>';
      });
  }

  function escapeHTMLText(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  if (loadBtn && loadModal) {
    loadBtn.addEventListener("click", function () {
      loadSearch.value = "";
      fetchQueries("");
      showModal(loadModal);
      loadSearch.focus();
    });
  }

  if (loadSearch) {
    var loadDebounce = null;
    loadSearch.addEventListener("input", function () {
      clearTimeout(loadDebounce);
      loadDebounce = setTimeout(function () {
        fetchQueries(loadSearch.value.trim());
      }, 300);
    });
  }

  // Ctrl+Enter to submit
  editor.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      submitForm();
    }
  });

  // Tab inserts spaces
  editor.addEventListener("keydown", function (e) {
    if (e.key === "Tab") {
      e.preventDefault();
      var start = editor.selectionStart;
      var end = editor.selectionEnd;
      editor.value = editor.value.substring(0, start) + "  " + editor.value.substring(end);
      editor.selectionStart = editor.selectionEnd = start + 2;
      syncHighlight();
    }
  });

  // SQL keyword toolbar
  document.querySelectorAll(".kw-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      insertAtCursor(btn.dataset.keyword);
      syncHighlight();
    });
  });

  // Schema sidebar: click table name to insert
  document.querySelectorAll(".schema-table").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      insertAtCursor(el.dataset.table);
      syncHighlight();
    });
  });

  // Schema sidebar: click column name to insert
  document.querySelectorAll(".schema-col").forEach(function (el) {
    el.addEventListener("click", function () {
      insertAtCursor(el.dataset.col);
      syncHighlight();
    });
  });


  // CSV download is now a server-side form POST (no JS needed)

  function insertAtCursor(text) {
    var start = editor.selectionStart;
    var before = editor.value.substring(0, start);
    var after = editor.value.substring(editor.selectionEnd);
    var needsSpace = before.length > 0 && !before.endsWith(" ") && !before.endsWith("\n");
    var insert = (needsSpace ? " " : "") + text;
    editor.value = before + insert + after;
    editor.selectionStart = editor.selectionEnd = start + insert.length;
    editor.focus();
  }

  // --- Column toggle in results ---

  var resultHeaders = document.querySelectorAll(".results-pane th[data-col-name]");
  if (resultHeaders.length > 0) {
    var allColumns = Array.from(resultHeaders).map(function (th) {
      return th.dataset.colName;
    });
    var selected = new Set(allColumns);

    resultHeaders.forEach(function (th) {
      th.addEventListener("click", function () {
        var col = th.dataset.colName;
        var idx = th.dataset.colIndex;

        if (selected.has(col)) {
          selected.delete(col);
        } else {
          selected.add(col);
        }

        if (selected.size === 0) {
          allColumns.forEach(function (c) { selected.add(c); });
        }

        var isSelected = selected.has(col);
        th.classList.toggle("col-deselected", !isSelected);
        document.querySelectorAll('td[data-col-index="' + idx + '"]').forEach(function (td) {
          td.classList.toggle("col-deselected", !isSelected);
        });

        editor.value = rewriteSQL(editor.value, allColumns, selected);
        syncHighlight();
      });
    });
  }

  // --- Cell click to add WHERE filter ---

  document.querySelectorAll(".results-pane td[data-col-index]").forEach(function (td) {
    td.addEventListener("click", function () {
      var idx = td.dataset.colIndex;
      var th = document.querySelector('.results-pane th[data-col-index="' + idx + '"]');
      if (!th) return;

      var colName = th.dataset.colName;
      var cellValue = td.textContent.trim();

      var condition;
      if (cellValue === "" || cellValue === "None") {
        condition = quoteIfNeeded(colName) + " IS NULL";
      } else {
        condition = quoteIfNeeded(colName) + " = '" + cellValue.replace(/'/g, "''") + "'";
      }

      editor.value = addWhereCondition(editor.value, condition);
      syncHighlight();

      td.classList.add("cell-filtered");
      setTimeout(function () { td.classList.remove("cell-filtered"); }, 600);
    });
  });

  function addWhereCondition(sql, condition) {
    var whereMatch = sql.match(/^([\s\S]+?)\bWHERE\b([\s\S]*)$/i);
    if (whereMatch) {
      var before = whereMatch[1] + "WHERE" + whereMatch[2];
      var trailingMatch = before.match(
        /^([\s\S]+?)(\s+(?:ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|OFFSET)\b[\s\S]*)$/i
      );
      if (trailingMatch) {
        return trailingMatch[1] + "\n  AND " + condition + trailingMatch[2];
      }
      return before + "\n  AND " + condition;
    }
    var trailingMatch = sql.match(
      /^([\s\S]+?)(\s+(?:ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|OFFSET)\b[\s\S]*)$/i
    );
    if (trailingMatch) {
      return trailingMatch[1] + "\nWHERE " + condition + trailingMatch[2];
    }
    return sql + "\nWHERE " + condition;
  }

  function rewriteSQL(sql, allCols, selectedCols) {
    var match = sql.match(/^(\s*SELECT\s+)([\s\S]+?)(\s+FROM\s+[\s\S]+)$/i);
    if (!match) return sql;
    var prefix = match[1];
    var fromClause = match[3];
    var cols;
    if (selectedCols.size === allCols.length) {
      cols = "*";
    } else {
      cols = allCols
        .filter(function (c) { return selectedCols.has(c); })
        .map(function (c) { return quoteIfNeeded(c); })
        .join(", ");
    }
    return prefix.replace(/SELECT\s+/i, "SELECT ") + cols + fromClause;
  }

  function quoteIfNeeded(name) {
    if (/^[a-z_][a-z0-9_]*$/.test(name)) return name;
    return '"' + name.replace(/"/g, '""') + '"';
  }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
