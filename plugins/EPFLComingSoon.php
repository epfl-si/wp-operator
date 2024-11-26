<?php

class EPFLComingSoonPlugin extends Plugin
{
	protected $pluginPath = "epfl-coming-soon/epfl-coming-soon.php";
	protected $epfl_csp_options = array (
		'status' => 'on',
		'theme_maintenance' => 'no',
		'status_code' => 'no',
		'page_title' => 'Coming soon',
		'page_content' => '&nbsp;  &nbsp; <p style="text-align: center;"><img class="img-fluid aligncenter" src="https://web2018.epfl.ch/5.0.2/icons/epfl-logo.svg" alt="Logo EPFL" width="388" height="113" /></p>  <h3 style="text-align: center; color: #ff0000; font-family: Helvetica, Arial, sans-serif;">Something new is coming...</h3> <p style="position: absolute; bottom: 0; left: 0; width: 100%; text-align: center;"><a href="wp-admin/">Connexion / Login</a></p>',
	);
}
