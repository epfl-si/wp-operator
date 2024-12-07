<?php
/**
 * In order to create the databases, its tables and put some content in it, the
 * operator need to call this script. This script is basically a minimalistic
 * "wp cli" that instanciate the WordPress framework and call the same functions
 * that the installer does, but does not require to have a valid WordPress
 * installation (a `wp-config.php` and `wp-includes/version.php` as the "wp cli"
 * does).
 *
 * As it's calling WordPress code, the `ABSPATH` constant has to be correctly
 * defined. It's meant to stand in the root of the wp-dev directory, but feel
 * free to have it pointing to any directory containing an extract of an
 * WordPress source. See the __WORDPRESS_SOURCE_DIR constant to change it.
 *
 * It also have to be able to connect to the database, so name equivalent to
 * `DB.wordpress-test.svc` have to be accessible. It means that if you want it
 * to work from outside the cluster, you have to use something like KubeVPN.
**/

error_log("  ...  Hello from wp-ops/ensure-wordpress-and-theme.php  ... ");

error_reporting(E_ALL);
ini_set('display_errors', 'On');

$shortops = "h";
$longopts  = array(
    "name:",
    "wp-dir:",
    "wp-host:",
    "db-host:",
    "db-name:",
    "db-user:",
    "db-password:",
);
$options = getopt($shortops, $longopts);
if ( key_exists("h", $options) ) {
  $help = <<<EOD

Usage:
  ensure-wordpress-and-theme.php --name="site-a" --path="/site-A"

Options:
  --name        Mandatory  Identifier (as in k8s CR's name). Example: "site-a"
  --wp-host     Mandatory  Hostname (“site_name”) for WordPress
  --db-host     Mandatory  Hostname of the database to connect to
  --db-user     Mandatory  Username of the database to connect to
  --db-password Mandatory  Password for the database to connect to
  --wp-dir      Mandatory  The path to the WordPress installation to load.
  --plugins     Mandatory  List of non-default plugins.
EOD;
  echo $help . "\n";
  exit();
}

function bad_option ($message) {
  echo $message;
  echo "\nUse -h to get additional help.\n";
  exit(1);
}

foreach(["name", "wp-dir", "wp-host",
         "db-host", "db-name", "db-user", "db-password"] as $opt) {
  if ( empty($options[$opt]) ) {
    bad_option("\"--$opt\" is required.");
  }
}

if ( empty($options["title"]) ) {
  $options["title"] = $options["name"];
}


define( 'ABSPATH', $options["wp-dir"]);
define( 'WP_CONTENT_DIR', ABSPATH);  # Meh.
define( 'WP_DEBUG', 1);
define( 'WP_DEBUG_DISPLAY', 1);

define( '__WORDPRESS_DOMAIN', $options["wp-host"] );
define( '__WORDPRESS_DEFAULT_THEME', 'wp-theme-2018' );

$_SERVER['HTTP_HOST'] = __WORDPRESS_DOMAIN;

define("DB_HOST", $options["db-host"]);
define("DB_NAME", $options["db-name"]);
define("DB_USER", $options["db-user"]);
define("DB_PASSWORD", $options["db-password"]);

global $table_prefix; $table_prefix = "wp_";

define("WP_ADMIN", true);
define("WP_INSTALLING", true);
require_once( ABSPATH . 'wp-settings.php' );

function ensure_plugins ( $options ) {
  # This is the default plugin list that should be activated at installation
  $plugins = array(
    "polylang/polylang.php",
    "EPFL-Content-Filter/EPFL-Content-Filter.php",
    "EPFL-settings/EPFL-settings.php",
    "accred/EPFL-Accred.php",
    "enlighter/Enlighter.php",
    "epfl-404/epfl-404.php",
    "epfl-cache-control/epfl-cache-control.php",
    "epfl-coming-soon/epfl-coming-soon.php",
    "epfl-intranet/epfl-intranet.php",
    // "epfl-menus/epfl-menus.php",
    "epfl-remote-content-shortcode/epfl-remote-content-shortcode.php",
    "ewww-image-optimizer/ewww-image-optimizer.php",
    "find-my-blocks/find-my-blocks.php",
    "flowpaper-lite-pdf-flipbook/flowpaper.php",
    "svg-support/svg-support.php",
    "tequila/EPFL-Tequila.php",
    "tinymce-advanced/tinymce-advanced.php",
    "very-simple-meta-description/vsmd.php",
    "wp-gutenberg-epfl/plugin.php",
    "wp-media-folder/wp-media-folder.php"
  );
  update_option( 'active_plugins', $plugins );
}

ensure_plugins( $options );

echo "WordPress plugins successfully installed";
