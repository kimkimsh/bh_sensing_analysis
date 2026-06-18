# BH Sensing Analysis

A local tool that organizes our meat sensing captures into a queryable database,
charts how the readings move by menu and date, and puts our recognition AI models side
by side on the same captures so you can see, and measure, where they agree and where
they pull apart.

---

## 1. Problem

Every cook on the grill produces sensor readings, and they pile up fast. On their own
they are just files in folders, with no index and no easy way to ask "show me this cut
over the last month."

The harder problem belongs to our sensing and ML team. When someone trains a new
recognition model, the captures have no ground-truth labels to grade it against. "How
accurate is the model" has no clean answer when there is nothing fixed to score it
against. So the data is hard to look at, and comparing one model to another has no fair
yardstick.

## 2. Solution

We built a small pipeline and dashboard. It reads the raw captures into a database,
scores each one, and compares recognition models on the same capture.

The comparison is the heart of it. Two models run over the identical capture, and the
tool lays their regions over the sensor's own view of the cook: grey where they agree,
and two colors for where each one reads meat alone. A few agreement numbers and a plain
caption sit underneath. Because the captures have no labels, the dashboard never calls
one model "more accurate." It reports agreement, the only honest claim when no ground
truth exists. The Compare tab leads with that picture; Trends and Explore add by-date
lines, by-menu bars, a model-versus-model scatter, and a clickable capture table. It
runs end to end, the offline tests pass, and the curated demo capture renders cleanly.

## 3. How AI is used

Two AIs show up here. The first is the one the tool studies: recognition runs on our
own AI models, and it has from the start. They are the subject of the whole tool, not a
side feature. The model decides where the meat is, and that decision is exactly what
gets measured and compared.

The second is the AI we built with. The tool was written with Claude (Claude Code) as a
multi-agent workflow: one pass to lock the shared contracts and tests, several agents in
parallel on ingestion, scoring, the database, and the dashboard, then a pass to wire it
together. Days of plumbing came together in one session.

## 4. Expected impact

This answers a question that comes up for us constantly: when we have a new recognition
model, is it ready, and where does it behave differently from the one we trust? Today an
engineer scrolls overlays and forms an opinion. This turns it into a number you can sort
by.

Within six weeks we can compare a new model against the current one across menus, rank
the cuts where they disagree most so review effort goes where it matters, and measure
how much faster the sign-off gets. Before, judging a model on unlabeled captures was a
gut read. After, every capture carries an agreement score and a visual diff. As GRILL X
moves into new markets and proteins, a standing tool that checks each new model on the
captures we already have keeps that check from becoming a bottleneck.

## 5. Walkthrough for judges

The demo runs locally in about a minute:

```
bash demo.sh
```

Leave the sidebar on Demo. It auto-selects a curated capture, so there is no hunting
through a table. Look at the overlap picture first: the background is the sensor's view
of the cook, grey is where both models agree, and the two colors are where they
disagree. Under it is the agreement number with a plain caption, ending on the honest
point that there are no labels, so this shows agreement, not accuracy. Then switch to
Explore for the by-date trends, by-menu bars, the model-versus-model scatter, and the
full table. Pick any row and Compare redraws for that capture, so it is not limited to
the one example.
