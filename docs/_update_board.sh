#!/bin/sh
# Writes the spec board's generated region in DOCS_DIR/specs/index.md, between
#
#   <!-- board:start -->
#   <!-- board:end -->
#
# and the generated Scope region in each DOCS_DIR/releases/*/index.md, between
#
#   <!-- scope:start -->
#   <!-- scope:end -->
#
# The board carries a Releases table, one row per release page with its scoped
# features' counts by State, and a Backlog of every non-Removed feature with
# no Iteration, grouped New / Deferred (tagged `deferred`) and by epic. A
# release's Scope table lists every feature whose own Iteration field points
# at that release. This mirrors Azure DevOps: Epic/Feature/User Story work
# items, State New|Active|Closed|Removed, the feature's Iteration field is the
# single source of truth for release assignment, and Tags carries `deferred`.
#
# Usage: _update_board.sh [--check] [DOCS_DIR]   (DOCS_DIR defaults to this script's directory)
#
# Reads the metadata table each epic, feature and release page carries
# directly under its title (a two-column "| | |" table with rows
# "| **Key** | Value |"), plus each epic's feature table:
#
#   DOCS_DIR/specs/epics/*/index.md   State, Tags, Start Date, Closed Date, Entry criteria
#   DOCS_DIR/specs/epics/*/F*.md      State, Parent, Iteration, Tags, Start Date,
#                                     Closed Date, Predecessors, Source, Entry criteria
#   DOCS_DIR/releases/*/index.md      Status, Start Date, Finish Date
#
# Exits 1 when: a page's metadata table is missing, out of order, has an
# unknown key, repeats a key, or has an invalid State/Status; a state-linked
# key (Start Date, Closed Date, Entry criteria) is present when it should not
# be, or missing when it should be present; an epic's feature table has no
# State column; a feature ID appears twice across epic tables; a feature's
# Iteration does not point to an existing release page; an Active feature has
# no Iteration; a shipped release has no Finish Date. With --check, both
# generated regions are left unchanged and the script also exits 1 when
# either is out of date. Every error is reported, not just the first.
set -eu

check=0
if [ "${1:-}" = "--check" ]; then
  check=1
  shift
fi
docs=${1:-$(dirname "$0")}
board=$docs/specs/index.md
self=$0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
: > "$tmp/errors"
err() { printf 'update_board: %s\n' "$1" >> "$tmp/errors"; }

: > "$tmp/epics.tsv"
: > "$tmp/features.tsv"
: > "$tmp/releases.tsv"
: > "$tmp/bare.tsv"

epicfiles=
for f in "$docs"/specs/epics/*/index.md; do
  [ -e "$f" ] && epicfiles="$epicfiles $f"
done
relfiles=
for f in "$docs"/releases/*/index.md; do
  [ -e "$f" ] && relfiles="$relfiles $f"
done

# ---------------------------------------------------------------------------
# Epics: DOCS_DIR/specs/epics/*/index.md
# ---------------------------------------------------------------------------
if [ -n "$epicfiles" ]; then
  # shellcheck disable=SC2086
  awk -v epics="$tmp/epics.tsv" -v errors="$tmp/errors" -v bare="$tmp/bare.tsv" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    function has_tag(tags, want,    n, i, parts) {
      n = split(tags, parts, ",")
      for (i = 1; i <= n; i++) if (trim(parts[i]) == want) return 1
      return 0
    }
    function check_meta(fname,    n, i, j, idx, lastidx, k, order, deferred) {
      if (!meta_ok) {
        print "update_board: " fname " has no metadata table directly after the title" >> errors
        return
      }
      n = split("State,Tags,Start Date,Closed Date,Entry criteria", order, ",")
      lastidx = 0
      delete seenkey
      for (i = 1; i <= mn; i++) {
        k = mkeys[i]
        idx = 0
        for (j = 1; j <= n; j++) if (order[j] == k) idx = j
        if (idx == 0) {
          print "update_board: " fname " metadata table has an unknown key: " k >> errors
          continue
        }
        if (k in seenkey) print "update_board: " fname " metadata table repeats the key " k >> errors
        seenkey[k] = 1
        if (idx <= lastidx) print "update_board: " fname " metadata table has " k " out of order" >> errors
        lastidx = idx
      }
      if (status != "New" && status != "Active" && status != "Closed" && status != "Removed")
        print "update_board: " fname " has an invalid State: " status >> errors
      deferred = has_tag(tags, "deferred")
      if (status == "Closed" && !("Closed Date" in mval))
        print "update_board: " fname " is Closed with no Closed Date row" >> errors
      if (status != "Closed" && ("Closed Date" in mval))
        print "update_board: " fname " has a Closed Date row but its State is not Closed" >> errors
      if ((status == "Active" || status == "Closed") && !("Start Date" in mval))
        print "update_board: " fname " is " status " with no Start Date row" >> errors
      if (status != "Active" && status != "Closed" && ("Start Date" in mval))
        print "update_board: " fname " has a Start Date row but its State is neither Active nor Closed" >> errors
      if (deferred && !("Entry criteria" in mval))
        print "update_board: " fname " is tagged deferred with no Entry criteria row" >> errors
      if (!deferred && ("Entry criteria" in mval))
        print "update_board: " fname " has an Entry criteria row but is not tagged deferred" >> errors
    }
    function flush_epic() {
      if (dir == "") return
      check_meta(FILENAME)
      printf "%d\t%s\t%s\t%s\t%s\t%d\t%d\n", enum, dir, title, status, crit, featn, has_tag(tags, "deferred") > epics
    }
    FNR == 1 {
      flush_epic()
      dir = FILENAME; sub(/\/index\.md$/, "", dir); sub(/.*\//, "", dir)
      epicid = dir; sub(/-.*/, "", epicid)
      enum = substr(epicid, 2) + 0
      title = ""; status = ""; crit = ""; tags = ""; col = 0; featn = 0
      metastate = 0; meta_ok = 0; mn = 0
      delete mval; delete mkeys
    }
    title == "" && /^# / { title = $0; sub(/^# /, "", title); metastate = 1; next }
    metastate == 1 && $0 == "" { next }
    metastate == 1 && $0 == "| | |" { metastate = 2; next }
    metastate == 1 { metastate = 9 }
    metastate == 2 && $0 == "| --- | --- |" { metastate = 3; meta_ok = 1; next }
    metastate == 2 { metastate = 9 }
    metastate == 3 && /^\|[^|]*\|[^|]*\|$/ {
      n = split($0, c, "|")
      k = trim(c[2])
      if (k ~ /^\*\*.+\*\*$/) {
        sub(/^\*\*/, "", k); sub(/\*\*$/, "", k)
        mv = trim(c[3])
        mn++; mkeys[mn] = k; mval[k] = mv
        if (k == "State") status = mv
        if (k == "Entry criteria") crit = mv
        if (k == "Tags") tags = mv
        next
      }
      metastate = 4
    }
    metastate == 3 { metastate = 4 }
    /^\|/ {
      n = split($0, c, "|")
      if (c[2] ~ /^[ :-]+$/) next
      if (!match(c[2], /F[0-9]+\.[0-9]+/)) {
        col = 0; tagcol = 0
        for (i = 2; i < n; i++) {
          h = trim(c[i])
          if (h == "State") col = i
          if (h == "Tags") tagcol = i
        }
        next
      }
      id = substr(c[2], RSTART, RLENGTH)
      featn++
      if (!col) {
        if (!(dir in nostatus)) print "update_board: " FILENAME " has a feature table with no State column" >> errors
        nostatus[dir] = 1
        next
      }
      if (id in idfile)
        print "update_board: " id " appears in two epic tables: " idfile[id] " and " FILENAME >> errors
      else
        idfile[id] = FILENAME
      # A row with no link cites no feature file; its own State/Tags cells,
      # not a metadata table, are the only source for it, so the board reads
      # them here instead of from a (nonexistent) F<n>.<m>.md.
      if (trim(c[2]) !~ /^\[/) {
        rowst = trim(c[col])
        rowtag = tagcol ? trim(c[tagcol]) : ""
        printf "%s\t%s\t%d\t%s\t%s\n", id, rowst, enum, dir, rowtag > bare
      }
    }
    END { flush_epic() }
  ' $epicfiles
fi

# ---------------------------------------------------------------------------
# Features: DOCS_DIR/specs/epics/*/F*.md — the source of truth for the board
# ---------------------------------------------------------------------------
featfiles=
for f in "$docs"/specs/epics/*/F*.md; do
  [ -e "$f" ] && featfiles="$featfiles $f"
done
if [ -n "$featfiles" ]; then
  # shellcheck disable=SC2086
  awk -v features="$tmp/features.tsv" -v errors="$tmp/errors" -v docs="$docs" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    function has_tag(tags, want,    n, i, parts) {
      n = split(tags, parts, ",")
      for (i = 1; i <= n; i++) if (trim(parts[i]) == want) return 1
      return 0
    }
    function release_num(link,    n) {
      if (!match(link, /release-[0-9]+/)) return ""
      return substr(link, RSTART, RLENGTH)
    }
    function check_meta(fname,    n, i, j, idx, lastidx, k, order, deferred, reldir) {
      if (!meta_ok) {
        print "update_board: " fname " has no metadata table directly after the title" >> errors
        return
      }
      n = split("State,Parent,Iteration,Tags,Start Date,Closed Date,Predecessors,Source,Entry criteria", order, ",")
      lastidx = 0
      delete seenkey
      for (i = 1; i <= mn; i++) {
        k = mkeys[i]
        idx = 0
        for (j = 1; j <= n; j++) if (order[j] == k) idx = j
        if (idx == 0) {
          print "update_board: " fname " metadata table has an unknown key: " k >> errors
          continue
        }
        if (k in seenkey) print "update_board: " fname " metadata table repeats the key " k >> errors
        seenkey[k] = 1
        if (idx <= lastidx) print "update_board: " fname " metadata table has " k " out of order" >> errors
        lastidx = idx
      }
      if (!("State" in mval)) print "update_board: " fname " metadata table has no State row" >> errors
      if (!("Parent" in mval)) print "update_board: " fname " metadata table has no Parent row" >> errors
      if (!("Predecessors" in mval)) print "update_board: " fname " metadata table has no Predecessors row" >> errors
      st = mval["State"]
      if (st != "New" && st != "Active" && st != "Closed" && st != "Removed")
        print "update_board: " fname " has an invalid State: " st >> errors
      deferred = has_tag(mval["Tags"], "deferred")
      if (st == "Closed" && !("Closed Date" in mval))
        print "update_board: " fname " is Closed with no Closed Date row" >> errors
      if (st != "Closed" && ("Closed Date" in mval))
        print "update_board: " fname " has a Closed Date row but its State is not Closed" >> errors
      if (deferred && !("Entry criteria" in mval))
        print "update_board: " fname " is tagged deferred with no Entry criteria row" >> errors
      if (!deferred && ("Entry criteria" in mval))
        print "update_board: " fname " has an Entry criteria row but is not tagged deferred" >> errors
      if (st == "Active" && !("Iteration" in mval))
        print "update_board: " fname " is Active with no Iteration row" >> errors
      if ("Iteration" in mval) {
        reldir = release_num(mval["Iteration"])
        if (reldir == "")
          print "update_board: " fname " has an Iteration row that names no release-<n>" >> errors
        else if (system("test -e \"" docs "/releases/" reldir "/index.md\"") != 0)
          print "update_board: " fname " has an Iteration row pointing at a release page that does not exist: " reldir >> errors
      }
    }
    function flush_feature() {
      if (fname == "") return
      check_meta(fname)
      id = fname; sub(/.*\//, "", id); sub(/-.*/, "", id); sub(/\.md$/, "", id)
      reldir = ("Iteration" in mval) ? release_num(mval["Iteration"]) : ""
      rnum = reldir; sub(/^release-/, "", rnum); rnum = (rnum == "") ? 0 : rnum + 0
      epicdir = fname; sub(/\/[^\/]*$/, "", epicdir); sub(/.*\//, "", epicdir)
      epicid = epicdir; sub(/-.*/, "", epicid); enum = substr(epicid, 2) + 0
      split(id, idparts, "."); fnum = idparts[2] + 0
      printf "%s\t%s\t%d\t%s\t%s\t%s\t%d\t%s\t%s\n", id, status_of(), enum, epicdir, fname, reldir, rnum, has_tag(mval["Tags"], "deferred"), mval["Entry criteria"] > features
    }
    function status_of() { return mval["State"] }
    FNR == 1 {
      flush_feature()
      fname = FILENAME
      metastate = 0; meta_ok = 0; mn = 0; title = ""
      delete mval; delete mkeys
    }
    title == "" && /^# / { title = $0; metastate = 1; next }
    metastate == 1 && $0 == "" { next }
    metastate == 1 && $0 == "| | |" { metastate = 2; next }
    metastate == 1 { metastate = 9 }
    metastate == 2 && $0 == "| --- | --- |" { metastate = 3; meta_ok = 1; next }
    metastate == 2 { metastate = 9 }
    metastate == 3 && /^\|[^|]*\|[^|]*\|$/ {
      n = split($0, c, "|")
      k = trim(c[2])
      if (k ~ /^\*\*.+\*\*$/) {
        sub(/^\*\*/, "", k); sub(/\*\*$/, "", k)
        v = trim(c[3])
        mn++; mkeys[mn] = k; mval[k] = v
        next
      }
      metastate = 4
    }
    metastate == 3 { metastate = 4 }
    END { flush_feature() }
  ' $featfiles
fi

# ---------------------------------------------------------------------------
# Releases: DOCS_DIR/releases/*/index.md
# ---------------------------------------------------------------------------
if [ -n "$relfiles" ]; then
  # shellcheck disable=SC2086
  awk -v releases="$tmp/releases.tsv" -v errors="$tmp/errors" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    function check_meta(fname,    n, i, j, idx, lastidx, k, order) {
      if (!meta_ok) {
        print "update_board: " fname " has no metadata table directly after the title" >> errors
        return
      }
      n = split("Status,Start Date,Finish Date", order, ",")
      lastidx = 0
      delete seenkey
      for (i = 1; i <= mn; i++) {
        k = mkeys[i]
        idx = 0
        for (j = 1; j <= n; j++) if (order[j] == k) idx = j
        if (idx == 0) {
          print "update_board: " fname " metadata table has an unknown key: " k >> errors
          continue
        }
        if (k in seenkey) print "update_board: " fname " metadata table repeats the key " k >> errors
        seenkey[k] = 1
        if (idx <= lastidx) print "update_board: " fname " metadata table has " k " out of order" >> errors
        lastidx = idx
      }
      if (status != "planned" && status != "in progress" && status != "shipped")
        print "update_board: " fname " has an invalid Status: " status >> errors
      if (status == "shipped" && !("Finish Date" in mval))
        print "update_board: " fname " is shipped with no Finish Date row" >> errors
      if (status != "shipped" && ("Finish Date" in mval))
        print "update_board: " fname " has a Finish Date row but its Status is not shipped" >> errors
    }
    function flush_release() {
      if (dir == "") return
      check_meta(FILENAME)
      statusline = status
      if ("Finish Date" in mval) statusline = status " (" mval["Finish Date"] ")"
      printf "%d\t%s\t%s\t%s\n", rnum, dir, title, statusline > releases
    }
    FNR == 1 {
      flush_release()
      dir = FILENAME; sub(/\/index\.md$/, "", dir); sub(/.*\//, "", dir)
      rnum = dir; sub(/^release-/, "", rnum); rnum = rnum + 0
      title = ""; status = ""; col = 0
      metastate = 0; meta_ok = 0; mn = 0
      delete mval; delete mkeys
    }
    title == "" && /^# / { title = $0; sub(/^# /, "", title); metastate = 1; next }
    metastate == 1 && $0 == "" { next }
    metastate == 1 && $0 == "| | |" { metastate = 2; next }
    metastate == 1 { metastate = 9 }
    metastate == 2 && $0 == "| --- | --- |" { metastate = 3; meta_ok = 1; next }
    metastate == 2 { metastate = 9 }
    metastate == 3 && /^\|[^|]*\|[^|]*\|$/ {
      n = split($0, c, "|")
      k = trim(c[2])
      if (k ~ /^\*\*.+\*\*$/) {
        sub(/^\*\*/, "", k); sub(/\*\*$/, "", k)
        v = trim(c[3])
        mn++; mkeys[mn] = k; mval[k] = v
        if (k == "Status") status = v
        next
      }
      metastate = 4
    }
    metastate == 3 { metastate = 4 }
    END { flush_release() }
  ' $relfiles
fi

# ---------------------------------------------------------------------------
# Cross-validation: a feature's Iteration names a release page that exists,
# checked above; here, a feature ID must exist in exactly one epic table.
# ---------------------------------------------------------------------------
awk -v epics="$tmp/epics.tsv" -v features="$tmp/features.tsv" -v errors="$tmp/errors" '
  BEGIN {
    while ((getline line < features) > 0) {
      split(line, f, "\t")
      seen[f[1]]++
    }
    close(features)
    for (id in seen) if (seen[id] > 1) print "update_board: " id " has more than one feature file" >> errors
  }
' /dev/null

# ---------------------------------------------------------------------------
# Backlog: every non-Removed feature with no Iteration, grouped New/Deferred.
# ---------------------------------------------------------------------------
: > "$tmp/backlog_combined.tsv"
awk -v errors="$tmp/errors" -v bf="$tmp/backlog_combined.tsv" '
  NF {
    split($0, f, "\t")
    id = f[1]; st = f[2]; enum_ = f[3]; dir = f[4]; fname = f[5]; reldir = f[6]; deferred = f[8]
    if (st == "Removed") next
    if (reldir != "") next
    file = fname; sub(/.*\//, "", file)
    split(id, v, "."); fnum = v[2] + 0
    if (deferred == "1") cls = "def"
    else if (st == "New") cls = "new"
    else next
    printf "%s\t%d\t%s\tF\t%d\t%s\t%s\t%s\n", cls, enum_, dir, fnum, id, st, file >> bf
  }
' "$tmp/features.tsv"

# A bare (fileless) epic-table row: its own State/Tags cells, joined with its
# epic's own deferred tag as a fallback when the row carries no Tags cell.
awk -v epics="$tmp/epics.tsv" -v bf="$tmp/backlog_combined.tsv" '
  BEGIN {
    while ((getline line < epics) > 0) {
      split(line, e, "\t")
      epicdeferred[e[2]] = e[7]
    }
    close(epics)
  }
  NF {
    split($0, f, "\t")
    id = f[1]; st = f[2]; enum_ = f[3]; dir = f[4]; rowtag = f[5]
    if (st == "Removed") next
    deferred = (rowtag == "deferred") ? "1" : epicdeferred[dir]
    split(id, idparts, "."); fnum = idparts[2] + 0
    if (deferred == "1") cls = "def"
    else if (st == "New") cls = "new"
    else next
    printf "%s\t%d\t%s\tF\t%d\t%s\t%s\t%s\n", cls, enum_, dir, fnum, id, st, "" >> bf
  }
' "$tmp/bare.tsv"

awk -v bf="$tmp/backlog_combined.tsv" '
  {
    split($0, e, "\t")
    enum_ = e[1]; dir = e[2]; status = e[4]; featn = e[6]; deferred = e[7]
    if (featn + 0 != 0) next
    if (status == "Removed" || status == "Closed") next
    if (status == "Active") next
    if (deferred == "1") cls = "def"
    else if (status == "New") cls = "new"
    else next
    printf "%s\t%d\t%s\tE\t0\t\t\t\n", cls, enum_, dir >> bf
  }
' "$tmp/epics.tsv"

sort -t "$(printf '\t')" -k1,1 -k2,2n -k5,5n "$tmp/backlog_combined.tsv" > "$tmp/backlog_combined.sorted.tsv"
sort -t "$(printf '\t')" -k1,1nr "$tmp/releases.tsv" > "$tmp/releases.sorted.tsv"

# ---------------------------------------------------------------------------
# Render the Backlog sections
# ---------------------------------------------------------------------------
: > "$tmp/backlog_section.new"
: > "$tmp/backlog_section.def"
awk -v epics="$tmp/epics.tsv" -v new="$tmp/backlog_section.new" -v def="$tmp/backlog_section.def" '
  BEGIN {
    while ((getline line < epics) > 0) {
      split(line, e, "\t")
      etitle[e[2]] = e[3]; ecrit[e[2]] = e[5]
    }
    close(epics)
    curclass = ""; curdir = ""; cells = ""
  }
  function epiclabel(dir) { return "[" etitle[dir] "](epics/" dir "/index.md)" }
  function flush_group() {
    if (curdir == "") return
    label = epiclabel(curdir)
    if (curclass == "new") print "| " label " | " cells " |" >> new
    else if (curclass == "def") {
      crit = ecrit[curdir]; if (crit == "") crit = "Per feature; see the epic."
      print "| " label " | " cells " | " crit " |" >> def
    }
  }
  {
    split($0, r, "\t")
    cls = r[1]; dir = r[3]; kind = r[4]; id = r[6]; file = r[8]
    if (dir != curdir || cls != curclass) { flush_group(); curclass = cls; curdir = dir; cells = "" }
    if (kind == "E") {
      cells = "\xe2\x80\x94"
    } else {
      if (file != "") txt = "[" id "](epics/" dir "/" file ")"
      else txt = id
      cells = (cells == "") ? txt : cells ", " txt
    }
  }
  END { flush_group() }
' "$tmp/backlog_combined.sorted.tsv"

# ---------------------------------------------------------------------------
# Render the Releases section
# ---------------------------------------------------------------------------
: > "$tmp/releases_section"
awk -v features="$tmp/features.tsv" '
  BEGIN {
    while ((getline line < features) > 0) {
      split(line, f, "\t")
      st = f[2]; rn = f[7]
      if (rn + 0 == 0) continue
      cnt[rn, st]++
      total[rn]++
    }
    close(features)
  }
  {
    split($0, r, "\t")
    rnum = r[1]; dir = r[2]; title = r[3]; statusline = r[4]
    parts = ""
    n1 = cnt[rnum, "Active"] + 0
    n2 = cnt[rnum, "New"] + 0
    n3 = cnt[rnum, "Closed"] + 0
    n4 = cnt[rnum, "Removed"] + 0
    if (n1) parts = parts (parts == "" ? "" : " \xc2\xb7 ") n1 " Active"
    if (n2) parts = parts (parts == "" ? "" : " \xc2\xb7 ") n2 " New"
    if (n3) parts = parts (parts == "" ? "" : " \xc2\xb7 ") n3 " Closed"
    if (n4) parts = parts (parts == "" ? "" : " \xc2\xb7 ") n4 " Removed"
    if (total[rnum] + 0 == 0) parts = "\xe2\x80\x94"
    printf "| [%s](../releases/%s/index.md) | %s | %s |\n", title, dir, statusline, parts
  }
' "$tmp/releases.sorted.tsv" > "$tmp/releases_section"

# ---------------------------------------------------------------------------
# Assemble the board's generated region
# ---------------------------------------------------------------------------
backlog_empty=1
[ -s "$tmp/backlog_section.new" ] && backlog_empty=0
[ -s "$tmp/backlog_section.def" ] && backlog_empty=0

{
  printf '%s\n' '<!-- board:start -->'
  printf '%s\n' '## Releases'
  printf '\n'
  printf '%s\n' '| Release | Status | Features |'
  printf '%s\n' '| --- | --- | --- |'
  cat "$tmp/releases_section"
  printf '\n'
  printf '%s\n' '## Backlog'
  printf '\n'
  if [ "$backlog_empty" -eq 1 ]; then
    printf '%s\n' 'Every feature is on a release or Removed.'
  else
    printf '%s\n' 'Features with no Iteration, by State and epic.'
    if [ -s "$tmp/backlog_section.new" ]; then
      printf '\n%s\n\n' '### New'
      printf '%s\n' '| Epic | Features |'
      printf '%s\n' '| --- | --- |'
      cat "$tmp/backlog_section.new"
    fi
    if [ -s "$tmp/backlog_section.def" ]; then
      printf '\n%s\n\n' '### Deferred'
      printf '%s\n' '| Epic | Features | Entry criteria |'
      printf '%s\n' '| --- | --- | --- |'
      cat "$tmp/backlog_section.def"
    fi
  fi
  printf '%s\n' '<!-- board:end -->'
} > "$tmp/region"

have_markers=1
grep -q '<!-- board:start -->' "$board" || { have_markers=0; err "$board has no <!-- board:start --> marker"; }
grep -q '<!-- board:end -->' "$board" || { have_markers=0; err "$board has no <!-- board:end --> marker"; }

if [ "$have_markers" -eq 1 ]; then
  awk -v region="$tmp/region" '
    /<!-- board:start -->/ { while ((getline line < region) > 0) print line; skip = 1; next }
    /<!-- board:end -->/ { skip = 0; next }
    !skip { print }
  ' "$board" > "$tmp/newboard"
  if ! cmp -s "$board" "$tmp/newboard"; then
    if [ "$check" -eq 1 ]; then
      err "$board is out of date; run $self $docs"
    else
      cp "$tmp/newboard" "$board"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Each release page's generated Scope region
# ---------------------------------------------------------------------------
for rf in $relfiles; do
  rdir=$(dirname "$rf"); rdir=${rdir##*/}
  : > "$tmp/scope_$rdir"

  awk -v features="$tmp/features.tsv" -v rdir="$rdir" '
    BEGIN {
      n = 0
      while ((getline line < features) > 0) {
        split(line, f, "\t")
        if (f[6] != rdir) continue
        n++
        id[n] = f[1]; st[n] = f[2]; enum_[n] = f[3]; edir[n] = f[4]; fname[n] = f[5]
      }
      close(features)
      for (i = 1; i <= n; i++) {
        for (j = i + 1; j <= n; j++) {
          if (id[i] > id[j]) {
            t = id[i]; id[i] = id[j]; id[j] = t
            t = st[i]; st[i] = st[j]; st[j] = t
            t = enum_[i]; enum_[i] = enum_[j]; enum_[j] = t
            t = edir[i]; edir[i] = edir[j]; edir[j] = t
            t = fname[i]; fname[i] = fname[j]; fname[j] = t
          }
        }
      }
      for (i = 1; i <= n; i++) {
        file = fname[i]; sub(/.*\//, "", file)
        printf "| [%s](../../specs/epics/%s/%s) | E%d | %s |\n", id[i], edir[i], file, enum_[i], st[i]
      }
    }
  ' /dev/null > "$tmp/scope_$rdir"

  {
    printf '%s\n' '<!-- scope:start -->'
    printf '%s\n' '<!-- generated by docs/_update_board.sh: do not edit -->'
    printf '%s\n' '| Feature | Epic | State |'
    printf '%s\n' '| --- | --- | --- |'
    if [ -s "$tmp/scope_$rdir" ]; then cat "$tmp/scope_$rdir"; fi
    printf '%s\n' '<!-- scope:end -->'
  } > "$tmp/scope_region_$rdir"

  if grep -q '<!-- scope:start -->' "$rf" && grep -q '<!-- scope:end -->' "$rf"; then
    awk -v region="$tmp/scope_region_$rdir" '
      /<!-- scope:start -->/ { while ((getline line < region) > 0) print line; skip = 1; next }
      /<!-- scope:end -->/ { skip = 0; next }
      !skip { print }
    ' "$rf" > "$tmp/newrelease_$rdir"
    if ! cmp -s "$rf" "$tmp/newrelease_$rdir"; then
      if [ "$check" -eq 1 ]; then
        err "$rf is out of date; run $self $docs"
      else
        cp "$tmp/newrelease_$rdir" "$rf"
      fi
    fi
  else
    err "$rf has no <!-- scope:start -->/<!-- scope:end --> marker pair"
  fi
done

status=0
if [ -s "$tmp/errors" ]; then
  cat "$tmp/errors" >&2
  status=1
fi
exit $status
