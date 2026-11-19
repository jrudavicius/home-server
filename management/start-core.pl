use strict;
use warnings;
use JSON::PP qw(decode_json encode_json);

# Keep the existing private cache format. Komodo interpolates its config files
# and trims native secret files, but accepts a literal string from its process environment.
my $key = eval {
    open my $cache, '<:raw', '/run/komodo-session/core.config.json' or die;
    local $/;
    decode_json(<$cache>)->{jwt_secret};
};
die "Komodo session signing file is missing or invalid\n"
    unless defined $key && encode_json($key) =~ /^"/ && length($key) && index($key, "\0") < 0;
die "Remove legacy JWT environment settings from Core after importing its signer\n"
    if exists $ENV{KOMODO_JWT_SECRET_FILE} || exists $ENV{KOMODO_JWT_SECRET};
utf8::encode($key);
$ENV{KOMODO_JWT_SECRET} = $key;

die "Komodo webhook secret file is missing or empty\n"
    if exists $ENV{KOMODO_WEBHOOK_SECRET_FILE} && !-s $ENV{KOMODO_WEBHOOK_SECRET_FILE};
exec 'core' or die "Could not start Komodo Core: $!\n";
