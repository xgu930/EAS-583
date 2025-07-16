// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "./BridgeToken.sol";

contract Destination is AccessControl {
    bytes32 public constant WARDEN_ROLE = keccak256("BRIDGE_WARDEN_ROLE");
    bytes32 public constant CREATOR_ROLE = keccak256("CREATOR_ROLE");
	mapping( address => address) public underlying_tokens;
	mapping( address => address) public wrapped_tokens;
	address[] public tokens;

	event Creation( address indexed underlying_token, address indexed wrapped_token );
	event Wrap( address indexed underlying_token, address indexed wrapped_token, address indexed to, uint256 amount );
	event Unwrap( address indexed underlying_token, address indexed wrapped_token, address frm, address indexed to, uint256 amount );


    constructor( address admin ) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(CREATOR_ROLE, admin);
        _grantRole(WARDEN_ROLE, admin);
    }

    // Custom errors
    error ZeroAddress();
    error ZeroAmount();
    error AlreadyRegistered();

    function _revertUnregistered() internal pure {
        assembly {
            mstore(0x00, 0xf4844814) // error selector
            revert(0x1c, 0x04)       // revert with 4‑byte data
        }
    }

	function wrap(address _underlying_token, address _recipient, uint256 _amount ) public onlyRole(WARDEN_ROLE) {
		//YOUR CODE HERE
		if (_recipient == address(0)) revert ZeroAddress();
        if (_amount == 0) revert ZeroAmount();

        address wrapped = underlying_tokens[_underlying_token];
        if (wrapped == address(0)) _revertUnregistered();

        emit Wrap(_underlying_token, wrapped, _recipient, _amount);
        BridgeToken(wrapped).mint(_recipient, _amount);

	}

	function unwrap(address _wrapped_token, address _recipient, uint256 _amount ) public {
		//YOUR CODE HERE
        if (_recipient == address(0)) revert ZeroAddress();
        if (_amount == 0) revert ZeroAmount();

		address underlying = wrapped_tokens[_wrapped_token];
        if (underlying == address(0)) _revertUnregistered();

		emit Unwrap(underlying,
                    _wrapped_token,
                    msg.sender,
                    _recipient,
                    _amount);

        BridgeToken(_wrapped_token).clawBack(msg.sender, _amount);
	}

	function createToken(address _underlying_token, string memory name, string memory symbol ) public onlyRole(CREATOR_ROLE) returns(address) {
		//YOUR CODE HERE
        if (_underlying_token == address(0)) revert ZeroAddress();
        if (underlying_tokens[_underlying_token] != address(0)) revert AlreadyRegistered();

        emit Creation(_underlying_token, address(0));
		BridgeToken wrapped =
        new BridgeToken(_underlying_token, name, symbol, address(this));
		underlying_tokens[_underlying_token] = address(wrapped);
        wrapped_tokens[address(wrapped)]     = _underlying_token;
        tokens.push(address(wrapped));

        return address(wrapped);
	}

}


