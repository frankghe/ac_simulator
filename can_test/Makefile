CC = gcc
CFLAGS = -Wall -g
SILKIT_HOME = /home/frank/projects/sil-kit
INCLUDES = -I$(SILKIT_HOME)/SilKit/include
LDFLAGS = -L$(SILKIT_HOME)/build/Release -lSilKit -Wl,-rpath,$(SILKIT_HOME)/build/Release

all: sender receiver

sender: can_send_test.c
	$(CC) $(CFLAGS) $(INCLUDES) -o can_send_test $< $(LDFLAGS)

receiver: can_receive_test.c
	$(CC) $(CFLAGS) $(INCLUDES) -o can_receive_test $< $(LDFLAGS)

clean:
	rm -f can_send_test can_receive_test

.PHONY: all sender receiver clean 