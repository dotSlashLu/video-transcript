SHELL := /bin/bash
BUILD := .build
SWIFTC := swiftc -O

.PHONY: all clean doctor test version install

all: $(BUILD)/vocr $(BUILD)/transcribe $(BUILD)/probe_speech
	@echo "built: $(BUILD)/{vocr,transcribe,probe_speech}"

$(BUILD)/vocr: cli/vocr.swift
	@mkdir -p $(BUILD)
	$(SWIFTC) $< -o $@

$(BUILD)/transcribe: cli/transcribe.swift
	@mkdir -p $(BUILD)
	$(SWIFTC) $< -o $@

$(BUILD)/probe_speech: cli/probe_speech.swift
	@mkdir -p $(BUILD)
	$(SWIFTC) $< -o $@

# Show which speech locales this Mac supports / already has installed.
doctor: $(BUILD)/probe_speech
	@./$(BUILD)/probe_speech

# End-to-end smoke test: synthesize 2s of silence, run the ASR channel.
test: all
	@python3 cli/vsum.py --version
	@ffmpeg -v error -f lavfi -i anullsrc=r=16000:cl=mono -t 2 -y /tmp/vsum-silence.wav
	@python3 cli/vsum.py /tmp/vsum-silence.wav --format json --quiet \
	  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("smoke ok, channel =", d["method"])'
	@rm -f /tmp/vsum-silence.wav

install:
	./install.sh --yes --link

version:
	@python3 cli/vsum.py --version

clean:
	rm -rf $(BUILD) out
