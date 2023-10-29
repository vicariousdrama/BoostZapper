# TODO Items

## Package user data

Consider adding a command to return all of a user's data

1. collect and create a tarball of the data 
2. encrypt the tarball with a password
3. upload the file to a publicly accessible link
4. return the link as a DM response to command

```sh
# Tar all files from an npub
cd /home/vic/BoostZapper/data
find . -name '*npub1yadayada*' -print0 | tar -cvjf /tmp/npub1yadayada.tar --null --files-from -
# Encrypt with ccrypt
```

