# Theseus user-guide build targets.
#
# House rule: compile with pdflatex. `make` (no arg) is equivalent to
# `make all`, which invokes build_pdfs.sh.  Per-guide targets exist for
# fast iteration on a single guide; they do not run the cross-link or
# size checks --- run `make all` to validate before committing.

GUIDES := \
    01_Theseus_Quick_Start \
    02_Knowledge_and_Principles \
    03_The_Oracle \
    04_Currents \
    05_Forecasts_and_Portfolio \
    06_Operator_Console

PDFS := $(addsuffix .pdf,$(GUIDES))

.PHONY: all clean distclean $(GUIDES)

all:
	./build_pdfs.sh

# Per-guide target: `make 03_The_Oracle` rebuilds only that guide.
$(GUIDES): %: %.tex _preamble.tex
	pdflatex -interaction=nonstopmode -halt-on-error $<
	pdflatex -interaction=nonstopmode -halt-on-error $<

# Per-PDF alias: `make 03_The_Oracle.pdf` also works.
%.pdf: %.tex _preamble.tex
	pdflatex -interaction=nonstopmode -halt-on-error $<
	pdflatex -interaction=nonstopmode -halt-on-error $<

clean:
	rm -f *.aux *.log *.out *.toc *.fls *.fdb_latexmk *.synctex.gz

distclean: clean
	rm -f $(PDFS)
